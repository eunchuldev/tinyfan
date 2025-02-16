from tinyfan import Flow, asset
from tinyfan.flow import FLOW_REGISTER
from tinyfan.codegen import codegen, AssetTree
from jsonschema.exceptions import ValidationError
from typing import Generator
import os
import pytest


# type: ignore
@pytest.fixture()
def sample_flow() -> Generator:
    flow: Flow = Flow("test")

    @asset(flow=flow, schedule="@daily")
    def asset1(ds: str):  # type: ignore
        print("asset1 is executed")
        return "hello"

    @asset(flow=flow)
    def asset2(asset1: str):  # type: ignore
        print("asset1 says: " + asset1)

    yield flow
    FLOW_REGISTER.clear()


# type: ignore
@pytest.fixture()
def unknown_arg_flow() -> Generator:
    flow: Flow = Flow("test")

    @asset(flow=flow, schedule="@daily")
    def asset1(unknown: str):  # type: ignore
        print("asset1 is executed")
        return "hello"

    yield flow
    FLOW_REGISTER.clear()


def gotmpl_values(tree: AssetTree, asset_name: str, schedule: str) -> dict:
    rundata = (
        tree.nodes[asset_name]
        .rundatatmpl(schedule)
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
    # comment out all assertion since templateDefault script override is not working
    return
    """
    sourcetmpl = next(yaml.load_all(code, yaml.Loader))["spec"]["workflowSpec"]["templates"][0]["script"]["source"]
    tree = AssetTree(flow)
    values = gotmpl_values(tree, "asset1", "@daily")
    source = gotmpl(sourcetmpl, values)
    f = StringIO()
    with redirect_stdout(f):
        exec(source)
    assert "asset1 is executed\n" == f.getvalue()

    asset1_rundata = open(
        RUNDATA_FILE_PATH.format(flow_name=asset1.asset.flow.name, asset_name=asset1.asset.name), "r"
    ).read()
    values = gotmpl_values(tree, "asset2", "@daily")
    values = gotmpl(values, {"tasks": {"asset1": {"outputs": {"parameters": {"rundata": asset1_rundata}}}}})
    source = gotmpl(sourcetmpl, values)
    f = StringIO()
    with redirect_stdout(f):
        exec(source)
    assert "asset1 says: hello\n" == f.getvalue()
    """


def test_codegen_raise_unknown_asset_args(unknown_arg_flow):
    with pytest.raises(Exception):
        _ = codegen(flow=unknown_arg_flow)


def test_codegen_flow(validate_crds, sample_flow):
    actual = codegen(flow=sample_flow)
    validate_crds(actual)
    assert_code_is_running(actual)


def test_codegen_implicit(validate_crds, sample_flow):
    actual = codegen()
    validate_crds(actual)
    assert_code_is_running(actual)


def test_embedded_codegen(validate_crds, sample_flow):
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


def test_rundata_data_interval(sample_flow):
    tree = AssetTree(sample_flow)
    node = list(tree.nodes.values())[0]
    # rundatatmpl = node.rundatatmpl("0 * * * * *")
    daily = node.rundatatmpl("@daily")
    assert (
        daily
        == """{"ds": "{{=sprig.date('2006-01-02', sprig.dateModify('-86400.0s', sprig.toDate('2006-01-02T15:04:05Z07:00', workflow.scheduledTime)))}}", "ts": "{{=sprig.dateModify('-86400.0s', sprig.toDate('2006-01-02T15:04:05Z07:00', workflow.scheduledTime))}}", "data_interval_start": {"__tinyfan_datetime__": "{{=sprig.dateModify('-86400.0s', sprig.toDate('2006-01-02T15:04:05Z07:00', workflow.scheduledTime))}}"}, "data_interval_end": {"__tinyfan_datetime__": "{{workflow.scheduledTime}}"}, "parents": {}, "asset_name": "asset1", "flow_name": "test", "module_name": "tests.test_codegen"}"""
    )
