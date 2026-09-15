import io
import os.path
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest


@pytest.mark.parametrize("minify", [False, True])
def test_embed_singlefile(tmp_path, minify):
    from tinyfan.utils.embed import embed_singlefile

    script = tmp_path / "main.py"
    script.write_text(
        "from __future__ import annotations\n"
        "from dataclasses import dataclass\n"
        "from pathlib import Path\n"
        "import helper\n"
        "@dataclass\n"
        "class Message:\n"
        "    value: str\n"
        "def message():\n"
        "    return Message(Path(__file__).with_name('DATA').read_text() + helper.VALUE).value",
        encoding="utf-8",
    )
    (tmp_path / "helper.py").write_text("VALUE = ' world'", encoding="utf-8")
    (tmp_path / "DATA").write_text("hello", encoding="utf-8")
    snippet = embed_singlefile(str(script), minify=minify)
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-"],
        input="import sys\n" + snippet + "print(message())\n",
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "hello world"


def test_embed_directory():
    from tinyfan.utils.embed import embed_directory

    p = os.path.join(os.path.dirname(__file__), "embed_samples/directory")
    snippet = embed_directory(p)
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-"],
        input=snippet + "\nimport directory\n",
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "hi\n"


def test_embed_module():
    from tinyfan.utils.embed import embed_module

    snippet = embed_module("tinyfan", excludes=["codegen.py", "utils/embed.py", "**/__pycache__/*"], minify=True)
    assert len(snippet) < 64 * 1000
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-"],
        input=snippet
        + "from tinyfan import Flow, asset\n"
        + 'flow = Flow("test-flow")\n'
        + "@asset(flow=flow)\n"
        + "def asset1():\n"
        + '    return "test"\n'
        + 'res, _ = flow.assets["asset1"].run()\n'
        + 'assert res == "test"\n',
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("minify", [False, True])
def test_embed_preserves_runtime_annotations(tmp_path, minify):
    from tinyfan.utils.embed import embed

    package = tmp_path / "typed_package"
    package.mkdir()
    package.joinpath("__init__.py").write_text(
        "from dataclasses import dataclass\n"
        "from typing import cast\n"
        "from pathlib import Path\n"
        "from importlib.resources import files\n"
        "from .namespace.helper import VALUE\n"
        "assert Path(__file__).with_name('DATA').read_text() == VALUE\n"
        "assert files(__package__).joinpath('assets.v1', 'query.sql').read_text() == 'SELECT 1'\n"
        "@dataclass\n"
        "class Result:\n"
        "    value: str\n"
        'print(Result(cast(str, "annotations preserved")).value)\n',
        encoding="utf-8",
    )
    package.joinpath("DATA").write_text("data", encoding="utf-8")
    package.joinpath("assets.v1").mkdir()
    package.joinpath("assets.v1", "query.sql").write_text("SELECT 1", encoding="utf-8")
    package.joinpath("namespace").mkdir()
    package.joinpath("namespace", "helper.py").write_text("VALUE = 'data'", encoding="utf-8")
    source = embed(str(package), minify=minify) + "\nimport typed_package\n"
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-"], input=source, capture_output=True, text=True, check=False, timeout=30
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "annotations preserved"


def test_zip_directory_selection_and_reproducibility(tmp_path):
    from tinyfan.utils.embed import zip_directory

    (tmp_path / "DATA").write_bytes(b"\x00\xff")
    (tmp_path / "main.py").write_text("value = 1", encoding="utf-8")
    for name in ("__pycache__", ".venv", ".git", "excluded"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "data.bin").write_bytes(b"not included")
    first, name = zip_directory(str(tmp_path))
    os.utime(tmp_path / "main.py", (0, 0))
    assert zip_directory(str(tmp_path))[0] == first
    with zipfile.ZipFile(io.BytesIO(first)) as zf:
        assert zf.namelist() == [f"{name}/DATA", f"{name}/excluded/data.bin", f"{name}/main.py"]
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in zf.infolist())
    selected, _ = zip_directory(str(tmp_path), includes=["**/*"], excludes=["excluded", "**/.*", "__pycache__"])
    with zipfile.ZipFile(io.BytesIO(selected)) as zf:
        assert zf.namelist() == [f"{name}/DATA", f"{name}/main.py"]


@pytest.mark.parametrize("entry", ["nested_embed.child", "nested_embed.child.module", "directory"])
def test_embed_nested_packages(tmp_path, monkeypatch, entry):
    from tinyfan.utils.embed import embed_directory, embed_module

    package = tmp_path / "nested_embed"
    child = package / "child"
    child.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "helper.py").write_text("VALUE = 'nested'", encoding="utf-8")
    (child / "__init__.py").write_text("from .module import VALUE", encoding="utf-8")
    (child / "module.py").write_text("from ..helper import VALUE", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        snippet = embed_directory(str(child), "nested_embed.child") if entry == "directory" else embed_module(entry)
        result = subprocess.run(
            [sys.executable, "-I", "-S", "-"],
            input=snippet + "from nested_embed.child.module import VALUE\nprint(VALUE)\n",
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "nested"
    finally:
        for name in list(sys.modules):
            if name == "nested_embed" or name.startswith("nested_embed."):
                sys.modules.pop(name)


def test_embed_errors_and_no_import_side_effects(tmp_path, monkeypatch):
    from tinyfan.utils.embed import embed, embed_singlefile, zip_directory

    monkeypatch.syspath_prepend(str(tmp_path))
    (tmp_path / "missing_dependency.py").write_text("import no_such_embed_dependency", encoding="utf-8")
    snippet = embed("missing_dependency")
    assert "missing_dependency" not in sys.modules
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-"],
        input=snippet + "import missing_dependency\n",
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode != 0
    assert "No module named 'no_such_embed_dependency'" in result.stderr
    with pytest.raises(ModuleNotFoundError):
        embed("no_such_embed_module")
    with pytest.raises(FileNotFoundError):
        embed(str(tmp_path / "missing"))
    with pytest.raises(ValueError, match="No files selected"):
        zip_directory(str(tmp_path), includes=[])
    (tmp_path / "data.txt").write_text("data", encoding="utf-8")
    with pytest.raises(ValueError, match="entry script was excluded"):
        embed_singlefile(str(tmp_path / "missing_dependency.py"), includes=["*.txt"])
    broken = tmp_path / "broken_embed"
    broken.mkdir()
    (broken / "__init__.py").write_text("import no_such_embed_dependency", encoding="utf-8")
    with pytest.raises(ModuleNotFoundError) as error:
        embed("broken_embed.child")
    assert error.value.name == "no_such_embed_dependency"


def test_embed_rejects_unsupported_modules(tmp_path, monkeypatch):
    from tinyfan.utils.embed import embed_module, zip_directory

    monkeypatch.syspath_prepend(str(tmp_path))
    (tmp_path / "namespace_embed").mkdir()
    for name in ("sys", "namespace_embed"):
        with pytest.raises(ValueError, match="expected Python source"):
            embed_module(name)
    (tmp_path / "native.pyd").write_bytes(b"native code")
    with pytest.raises(ValueError, match="native library"):
        zip_directory(str(tmp_path))


def test_embed_precedence_and_cleanup(tmp_path):
    from tinyfan.utils.embed import embed_directory

    package = tmp_path / "bundled"
    package.mkdir()
    (package / "__init__.py").write_text("VALUE = 'bundled'", encoding="utf-8")
    existing = tmp_path / "existing"
    existing.mkdir()
    (existing / "bundled.py").write_text("VALUE = 'existing'", encoding="utf-8")
    # Concatenating bundles must retain each directory until process exit.
    second = tmp_path / "second"
    second.mkdir()
    (second / "__init__.py").write_text("VALUE = 'second'", encoding="utf-8")
    source = f"import sys\nsys.path.insert(0, {str(existing)!r})\n"
    source += embed_directory(str(package)) + embed_directory(str(second))
    source += (
        "import bundled, second\nprint(bundled.VALUE, second.VALUE)\nprint(bundled.__file__)\nprint(second.__file__)\n"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-"],
        input=source,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    values, first_file, second_file = result.stdout.splitlines()
    assert values == "bundled second"
    assert not Path(first_file).parent.parent.exists()
    assert not Path(second_file).parent.parent.exists()
