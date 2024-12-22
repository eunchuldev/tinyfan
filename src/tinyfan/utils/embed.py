import os
import base64
import importlib
import zipfile
from pathlib import Path
import io
import ast

DEFAULT_INCLUDES = ["**/*.*"]
DEFAULT_EXCLUDES = ["**/__pycache__/*"]


class TypeHintRemover(ast.NodeTransformer):
    def visit_FunctionDef(self, node):
        node.returns = None
        if node.args.args:
            for arg in node.args.args:
                arg.annotation = None
        self.generic_visit(node)
        return node

    def visit_AnnAssign(self, node):
        if node.value is None:
            return None
        return ast.Assign([node.target], node.value)

    def visit_Import(self, node):
        node.names = [n for n in node.names if n.name != "typing"]
        return node if node.names else None

    def visit_ImportFrom(self, node):
        return node if node.module != "typing" else None


def remove_type_hint(source: str):
    parsed_source = ast.parse(source)
    transformed = TypeHintRemover().visit(parsed_source)
    return ast.unparse(ast.fix_missing_locations(transformed))


def zip_directory(
    dir_path: str,
    includes: list[str] = DEFAULT_INCLUDES,
    excludes: list[str] = DEFAULT_EXCLUDES,
    minify: bool = False,
) -> tuple[bytes, str]:
    dir_path = os.path.abspath(dir_path)
    parent_dir = os.path.dirname(dir_path)
    base_name = os.path.basename(dir_path)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        path = Path(dir_path)
        files = set().union(*map(path.glob, includes))
        files -= set().union(*map(path.glob, excludes))
        for file_path in map(str, files):
            arcname = os.path.relpath(file_path, start=parent_dir)
            with open(file_path, "r") as f:
                try:
                    source = f.read()
                except Exception as e:
                    raise ValueError(f"fail to zip directory {dir_path}: fail to read file {file_path}") from e
            if minify:
                source = remove_type_hint(source)
            zf.writestr(arcname, source)
    buf.seek(0)
    return buf.read(), base_name


def embed_singlefile(path: str) -> str:
    with open(path, "r") as f:
        sourcecode = f.read()
    return sourcecode


def embed_directory(
    dir_path: str,
    main_module: str | None = None,
    includes: list[str] = DEFAULT_INCLUDES,
    excludes: list[str] = DEFAULT_EXCLUDES,
    minify=True,
) -> str:
    zip_bytes, base_name = zip_directory(dir_path, includes, excludes, minify)
    encoded = base64.b64encode(zip_bytes).decode("utf-8")
    snippet = f"""
import sys, base64, tempfile
zip_data = base64.b64decode('{encoded}')
with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp_file:
    tmp_file.write(zip_data)
    sys.path.append(tmp_file.name)
"""
    # snippet += f'import {main_module or base_name}\n'
    return snippet


def embed_path(
    path: str,
    main_module: str | None = None,
    includes: list[str] = DEFAULT_INCLUDES,
    excludes: list[str] = DEFAULT_EXCLUDES,
) -> str:
    if os.path.isfile(path):
        return embed_singlefile(path)
    else:
        return embed_directory(path, main_module, includes, excludes)


def embed_module(
    module_name: str,
    includes: list[str] = DEFAULT_INCLUDES,
    excludes: list[str] = DEFAULT_EXCLUDES,
    minify=True,
) -> str:
    mod = importlib.import_module(module_name)
    if mod.__file__ is None:
        raise ValueError(f"{module_name}.__file__ is None.")
    pkg_dir = os.path.dirname(mod.__file__)
    return embed_directory(pkg_dir, module_name, includes, excludes, minify)


def embed(
    path_or_module: str,
    includes: list[str] = DEFAULT_INCLUDES,
    excludes: list[str] = DEFAULT_EXCLUDES,
    minify=False,
) -> str:
    try:
        return embed_module(path_or_module, includes, excludes, minify)
    except ModuleNotFoundError:
        return embed_path(path_or_module, None, includes, excludes)
