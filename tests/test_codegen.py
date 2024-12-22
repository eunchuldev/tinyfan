from tinyfan import Flow, asset
from tinyfan.codegen import codegen, AssetTree, RUNDATA_FILE_PATH
from jsonschema.exceptions import ValidationError
from io import StringIO
import os
from contextlib import redirect_stdout
from .helpers import gotmpl
import yaml

flow: Flow = Flow("test")


@asset(flow=flow, schedule="@daily")
def asset1():
    print("asset1 is executed")
    return "hello"


@asset(flow=flow)
def asset2(asset1: str):
    print("asset1 says: " + asset1)


def gotmpl_values(tree: AssetTree, asset_name: str) -> dict:
    rundata = (
        tree.nodes[asset_name]
        .rundatatmpl()
        .replace("{{=sprig.date(workflow.scheduledTime)}}", "2023-01-01")
        .replace("{{workflow.scheduledTime}}", "2023-01-01T00:00:00")
    )
    return {
        "tasks": {"name": asset_name},
        "inputs": {
            "parameters": {
                "rundata": rundata,
                "asset_name": asset_name,
                "module_name": tree.nodes[asset_name].asset_module_name(),
            }
        },
    }


def assert_code_is_running(code: str):
    sourcetmpl = next(yaml.load_all(code, yaml.Loader))["spec"]["templateDefaults"]["script"]["source"]
    tree = AssetTree(flow)
    values = gotmpl_values(tree, "asset1")
    source = gotmpl(sourcetmpl, values)
    f = StringIO()
    with redirect_stdout(f):
        exec(source)
    assert "asset1 is executed\n" == f.getvalue()

    asset1_rundata = open(
        RUNDATA_FILE_PATH.format(flow_name=asset1.asset.flow.name, asset_name=asset1.asset.name), "r"
    ).read()
    values = gotmpl_values(tree, "asset2")
    values = gotmpl(values, {"tasks": {"asset1": {"outputs": {"parameters": {"rundata": asset1_rundata}}}}})
    source = gotmpl(sourcetmpl, values)
    f = StringIO()
    with redirect_stdout(f):
        exec(source)
    assert "asset1 says: hello\n" == f.getvalue()


def test_codegen(validate_crds, assert_manifests):
    actual = codegen()
    validate_crds(actual)
    assert_code_is_running(actual)


def test_embedded_codegen(validate_crds, assert_manifests):
    actual = codegen(embedded=True)
    validate_crds(actual)
    assert_code_is_running(actual)


def test_codegen_singlefile(validate_crds):
    p = os.path.join(os.path.dirname(__file__), "codegen_samples/singlefile.py")
    actual = codegen(location=p)
    try:
        validate_crds(actual)
    except ValidationError as e:
        if e.json_path != "$.spec.templates[0].script" or e.validator != "required":
            raise e
    assert_code_is_running(actual)


def test_codegen_directory(validate_crds):
    p = os.path.join(os.path.dirname(__file__), "codegen_samples/directory")
    actual = codegen(location=p)
    try:
        validate_crds(actual)
    except ValidationError as e:
        if e.json_path != "$.spec.templates[0].script" or e.validator != "required":
            raise e
    assert_code_is_running(actual)
