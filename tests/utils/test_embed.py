import os.path
import pytest
import sys
from io import StringIO
from contextlib import redirect_stdout
from unittest.mock import patch


def test_embed_singlefile():
    from tinyfan.utils.embed import embed_singlefile

    p = os.path.join(os.path.dirname(__file__), "embed_samples/singlefile.py")
    snippet = embed_singlefile(p)
    assert 'print("embed singlefile")\n' == snippet


def test_embed_directory():
    from tinyfan.utils.embed import embed_directory

    p = os.path.join(os.path.dirname(__file__), "embed_samples/directory")
    snippet = embed_directory(p)
    f = StringIO()
    print(snippet)
    with redirect_stdout(f):
        exec(snippet)
        import directory # type: ignore # noqa
    assert "hi\n" == f.getvalue()


def test_embed_module():
    from tinyfan.utils.embed import embed_module

    snippet = embed_module("tinyfan", excludes=["codegen.py", "utils/embed.py", "**/__pycache__/*"], minify=True)
    assert len(snippet) < 64 * 1000
    sys.modules.pop("tinyfan", None)
    with patch.object(sys, "path", []):
        try:
            import tinyfan as _

            pytest.fail("Success to import tinyfan before deserializtion")
        except ImportError:
            pass

        exec(snippet)

        from tinyfan import Flow, asset

        flow = Flow("test-flow")

        @asset(flow=flow)
        def asset1():
            return "test"

        res, _ = flow.assets["asset1"].run()
        assert res == "test"
