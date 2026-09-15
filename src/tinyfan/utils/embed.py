import ast
import base64
import importlib.util
import io
import os
import zipfile
from collections.abc import Iterable
from pathlib import Path

DEFAULT_INCLUDES = ["**/*"]
DEFAULT_EXCLUDES = [
    "**/__pycache__",
    "**/*.pyc",
    "**/*.pyo",
    "**/.git",
    "**/.venv",
    "**/venv",
    "**/.pytest_cache",
    "**/.mypy_cache",
    "**/.ruff_cache",
]


def _zip_files(files: Iterable[Path], root: Path, minify: bool) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(files):
            if path.suffix.lower() in {".so", ".pyd", ".dll", ".dylib"}:
                raise ValueError(f"Cannot embed native library {path}; install it in the container instead.")
            if path.is_symlink():
                raise ValueError(f"Cannot embed symbolic link {path}.")
            source = path.read_bytes()
            if minify and path.suffix == ".py":
                source = ast.unparse(ast.parse(source, filename=str(path))).encode("utf-8")
            # ZipInfo defaults to a fixed timestamp, keeping generated manifests reproducible.
            info = zipfile.ZipInfo(path.relative_to(root).as_posix())
            zf.writestr(info, source, compress_type=zipfile.ZIP_DEFLATED)
    return buf.getvalue()


def zip_directory(
    dir_path: str,
    includes: list[str] = DEFAULT_INCLUDES,
    excludes: list[str] = DEFAULT_EXCLUDES,
    minify: bool = False,
) -> tuple[bytes, str]:
    path = Path(dir_path).absolute()
    if not path.exists():
        raise FileNotFoundError(path)
    if not path.is_dir():
        raise NotADirectoryError(path)
    files = {file for pattern in includes for file in path.glob(pattern) if file.is_file()}
    excluded = {file for pattern in excludes for file in path.glob(pattern)}
    files = {file for file in files if file not in excluded and not excluded.intersection(file.parents)}
    if not files:
        raise ValueError(f"No files selected for embedding in {path}.")
    return _zip_files(files, path.parent, minify), path.name


def embed_singlefile(
    path: str,
    includes: list[str] = DEFAULT_INCLUDES,
    excludes: list[str] = DEFAULT_EXCLUDES,
    minify: bool = False,
    *,
    module_name: str = "__tinyfan_repo__",
) -> str:
    """Bundle a script's directory and execute the script as a real module."""
    source_path = Path(path).absolute()
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    if source_path.suffix != ".py":
        raise ValueError(f"Expected a Python source file: {source_path}")
    zip_bytes, directory = zip_directory(str(source_path.parent), includes, excludes, minify)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        if f"{directory}/{source_path.name}" not in zf.namelist():
            raise ValueError(f"The entry script was excluded from the bundle: {source_path}")
    return (
        embed_zip(zip_bytes)
        + f"""import importlib.util as _tinyfan_importlib, os as _tinyfan_os
_tinyfan_script = _tinyfan_os.path.join(_tinyfan_bundle.name, {directory!r}, {source_path.name!r})
_tinyfan_sys.path.insert(0, _tinyfan_os.path.dirname(_tinyfan_script))
_tinyfan_spec = _tinyfan_importlib.spec_from_file_location({module_name!r}, _tinyfan_script)
_tinyfan_module = _tinyfan_importlib.module_from_spec(_tinyfan_spec)
_tinyfan_sys.modules[{module_name!r}] = _tinyfan_module
_tinyfan_spec.loader.exec_module(_tinyfan_module)
globals().update({{k: v for k, v in vars(_tinyfan_module).items() if not k.startswith('__')}})
"""
    )


def embed_directory(
    dir_path: str,
    main_module: str | None = None,
    includes: list[str] = DEFAULT_INCLUDES,
    excludes: list[str] = DEFAULT_EXCLUDES,
    minify=False,
) -> str:
    """Bundle a directory, preserving regular parent packages; optionally import an entry module."""
    path = Path(dir_path).absolute()
    while (path / "__init__.py").is_file() and (path.parent / "__init__.py").is_file():
        path = path.parent
    zip_bytes, _ = zip_directory(str(path), includes, excludes, minify)
    snippet = embed_zip(zip_bytes)
    if main_module is not None:
        snippet += f"import importlib as _tinyfan_importlib\n_tinyfan_importlib.import_module({main_module!r})\n"
    return snippet


def embed_zip(zip_bytes: bytes) -> str:
    encoded = base64.b64encode(zip_bytes).decode("utf-8")
    snippet = f"""import atexit as _tinyfan_atexit, base64 as _tinyfan_base64, io as _tinyfan_io
import sys as _tinyfan_sys, tempfile as _tinyfan_tempfile, zipfile as _tinyfan_zipfile
_tinyfan_bundle = _tinyfan_tempfile.TemporaryDirectory(prefix='tinyfan-')
_tinyfan_atexit.register(_tinyfan_bundle.cleanup)
with _tinyfan_zipfile.ZipFile(_tinyfan_io.BytesIO(_tinyfan_base64.b64decode('{encoded}'))) as _tinyfan_zip:
    _tinyfan_zip.extractall(_tinyfan_bundle.name)
_tinyfan_sys.path.insert(0, _tinyfan_bundle.name)
"""
    return snippet


def embed_path(
    path: str,
    main_module: str | None = None,
    includes: list[str] = DEFAULT_INCLUDES,
    excludes: list[str] = DEFAULT_EXCLUDES,
    minify=False,
) -> str:
    if os.path.isfile(path):
        return embed_singlefile(path, includes, excludes, minify, module_name=main_module or "__tinyfan_repo__")
    else:
        return embed_directory(path, main_module, includes, excludes, minify)


def embed_module(
    module_name: str,
    includes: list[str] = DEFAULT_INCLUDES,
    excludes: list[str] = DEFAULT_EXCLUDES,
    minify=False,
) -> str:
    """Bundle a source module or its regular top-level package, without resolving dependencies."""
    spec = importlib.util.find_spec(module_name)
    if spec is None:
        raise ModuleNotFoundError(f"No module named {module_name!r}", name=module_name)
    if not spec.origin or not spec.origin.endswith(".py"):
        raise ValueError(f"Cannot embed {module_name!r}: expected Python source; install it in the container instead.")
    root_name = module_name.partition(".")[0]
    root_spec = importlib.util.find_spec(root_name)
    if root_spec is None or not root_spec.origin or not root_spec.origin.endswith(".py"):
        raise ValueError(f"Cannot embed namespace package {root_name!r}; use a regular package with __init__.py.")
    path = Path(root_spec.origin)
    if path.name == "__init__.py":
        return embed_directory(str(path.parent), includes=includes, excludes=excludes, minify=minify)
    # ponytail: an installed single-file module includes only its source; dependencies belong in the image.
    return embed_zip(_zip_files([path], path.parent, minify))


def embed(
    path_or_module: str,
    includes: list[str] = DEFAULT_INCLUDES,
    excludes: list[str] = DEFAULT_EXCLUDES,
    minify=False,
) -> str:
    if (
        os.path.exists(path_or_module)
        or any(sep in path_or_module for sep in ("/", "\\"))
        or path_or_module.endswith(".py")
    ):
        return embed_path(path_or_module, None, includes, excludes, minify)
    return embed_module(path_or_module, includes, excludes, minify)
