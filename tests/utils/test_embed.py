import os.path
import subprocess
import sys

import pytest


def test_embed_singlefile():
    from tinyfan.utils.embed import embed_singlefile

    p = os.path.join(os.path.dirname(__file__), "embed_samples/singlefile.py")
    snippet = embed_singlefile(p)
    assert 'print("embed singlefile")\n' == snippet


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
        "@dataclass\n"
        "class Result:\n"
        "    value: str\n"
        'print(Result(cast(str, "annotations preserved")).value)\n',
        encoding="utf-8",
    )
    source = embed(str(package), minify=minify) + "\nimport typed_package\n"
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-"], input=source, capture_output=True, text=True, check=False, timeout=30
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "annotations preserved"
