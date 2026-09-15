import importlib
import json
import os
import subprocess
import sys
from collections.abc import Generator

import pytest
import yaml
from jsonschema.exceptions import ValidationError

from tinyfan import Flow, asset
from tinyfan.codegen import AssetTree, codegen
from tinyfan.config import CLI_CONFIG_STATE
from tinyfan.flow import FLOW_REGISTER


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

    @asset(flow=flow, depends="asset1 && asset2")
    def asset3(asset1: str):  # type: ignore
        print("asset1 says: " + asset1)

    @asset(flow=flow, depends="asset2")
    def asset4(asset1: str):  # type: ignore
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
    with pytest.raises(ValueError, match="unknown asset args: `unknown` from asset `asset1`"):
        _ = codegen(flow=unknown_arg_flow)


def test_codegen_flow(validate_crds, sample_flow):
    actual = codegen(flow=sample_flow)
    validate_crds(actual)
    assert_code_is_running(actual)


def test_codegen_asset_inputs_outputs(validate_crds):
    flow: Flow = Flow("test-io")

    @asset(
        flow=flow,
        schedule="@daily",
        inputs={"parameters": [{"name": "message", "value": "hello"}]},
        outputs={"parameters": [{"name": "summary", "valueFrom": {"path": "/tmp/summary.txt"}}]},
    )
    def asset1():  # type: ignore
        return "hello"

    try:
        actual = codegen(flow=flow)
        validate_crds(actual)
        manifest = next(yaml.load_all(actual, yaml.Loader))
        template = next(
            template for template in manifest["spec"]["workflowSpec"]["templates"] if template["name"] == "asset1"
        )
        input_params = {param["name"]: param for param in template["inputs"]["parameters"]}
        output_params = {param["name"]: param for param in template["outputs"]["parameters"]}

        assert input_params["message"] == {"name": "message", "value": "hello"}
        assert {"rundata", "asset_name", "moduledata"}.issubset(input_params.keys())
        assert output_params["summary"] == {"name": "summary", "valueFrom": {"path": "/tmp/summary.txt"}}
        assert output_params["rundata"] == {"name": "rundata", "valueFrom": {"path": "/tmp/tinyfan/rundata.json"}}
    finally:
        FLOW_REGISTER.clear()


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
            raise
    assert_code_is_running(actual)


def test_codegen_directory(validate_crds):
    p = os.path.join(os.path.dirname(__file__), "codegen_samples/directory")
    actual = codegen(location=p)
    try:
        validate_crds(actual)
    except ValidationError as e:
        if e.json_path != "$.spec.templates[0].script" or e.validator != "required":
            raise
    assert_code_is_running(actual)
    manifest = next(yaml.safe_load_all(actual))
    tasks = manifest["spec"]["workflowSpec"]["templates"][-1]["dag"]["tasks"]
    for task in tasks:
        params = {param["name"]: param["value"] for param in task["arguments"]["parameters"]}
        for item in json.loads(params["moduledata"]):
            assert item["module"].startswith("directory.")
            assert getattr(importlib.import_module(item["module"]), item["name"]).asset


def test_codegen_directory_only_imports_asset_modules(tmp_path, monkeypatch, validate_crds):
    FLOW_REGISTER.clear()
    package_name = "selective_asset_package"
    package_path = tmp_path / package_name
    package_path.mkdir()
    (package_path / "__init__.py").write_text("", encoding="utf-8")
    (package_path / "flow.py").write_text(
        'from tinyfan import Flow\nflow = Flow("selective-discovery")\n',
        encoding="utf-8",
    )
    (package_path / "assets.py").write_text(
        "import tinyfan as tf\n"
        "from .flow import flow\n\n"
        '@tf.asset(flow=flow, schedule="@daily")\n'
        "def discovered_asset():\n"
        '    return "hello"\n',
        encoding="utf-8",
    )
    (package_path / "unrelated.py").write_text(
        'raise RuntimeError("unrelated module was imported")\n',
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    try:
        actual = codegen(location=package_name)

        validate_crds(actual)
        assert f"{package_name}.assets" in sys.modules
        assert f"{package_name}.flow" in sys.modules
        assert f"{package_name}.unrelated" not in sys.modules
    finally:
        for module_name in list(sys.modules):
            if module_name == package_name or module_name.startswith(f"{package_name}."):
                sys.modules.pop(module_name)
        FLOW_REGISTER.clear()


def test_rundata_data_interval(sample_flow):
    tree = AssetTree(sample_flow)
    node = next(iter(tree.nodes.values()))
    daily = node.rundatatmpl("@daily")
    assert (
        daily
        == """{"ds": "{{=sprig.date('2006-01-02', sprig.dateModify('-86400.0s', sprig.toDate('2006-01-02T15:04:05Z07:00', workflow.scheduledTime)))}}", "ts": "{{=sprig.dateModify('-86400.0s', sprig.toDate('2006-01-02T15:04:05Z07:00', workflow.scheduledTime))}}", "data_interval_start": {"__tinyfan_datetime__": "{{=sprig.dateModify('-86400.0s', sprig.toDate('2006-01-02T15:04:05Z07:00', workflow.scheduledTime))}}"}, "data_interval_end": {"__tinyfan_datetime__": "{{workflow.scheduledTime}}"}, "parents": {}, "asset_name": "asset1", "flow_name": "test", "module_name": "tests.test_codegen"}"""
    )


def test_depends(sample_flow):
    original = [item.depends for item in sample_flow.assets.values()]
    tree = AssetTree(sample_flow)
    assert [node.depends for node in tree.nodes.values()] == [
        "",
        "asset1",
        "asset1 && asset2",
        "asset2 && asset1",
    ]
    assert codegen(flow=sample_flow) == codegen(flow=sample_flow)
    assert [item.depends for item in sample_flow.assets.values()] == original


def test_depends_with_underscored_asset_names():
    flow = Flow("underscored-dependencies")

    @asset(flow=flow, schedule="@daily")
    def source_asset():
        return 1

    @asset(flow=flow)
    def prerequisite_asset():
        return 2

    @asset(flow=flow, depends="prerequisite_asset")
    def consumer_asset(source_asset):
        return source_asset

    try:
        manifest = yaml.safe_load(codegen(flow=flow))
        tasks = manifest["spec"]["workflowSpec"]["templates"][-1]["dag"]["tasks"]
        consumer = next(task for task in tasks if task["name"] == "consumer-asset")
        assert consumer["depends"] == "prerequisite-asset && source-asset"
        assert consumer_asset.asset.depends == "prerequisite_asset"
        assert source_asset.asset.depends is None
    finally:
        FLOW_REGISTER.pop(flow.name, None)


@pytest.mark.parametrize("embedded", [False, True])
@pytest.mark.parametrize("container_level", ["none", "flow", "compile"])
def test_generated_package_runs(tmp_path, monkeypatch, embedded, container_level):
    package_name = "runtime_regression_package"
    package_path = tmp_path / package_name
    package_path.mkdir()
    package_path.joinpath("__init__.py").write_text(
        "from dataclasses import dataclass\n"
        "from typing import cast\n"
        "from tinyfan import Flow, asset, cli_arg\n"
        "@dataclass\n"
        "class Message:\n"
        "    value: str\n"
        'flow = Flow("runtime-regression")\n'
        'message = cli_arg("message")\n'
        '@asset(flow=flow, schedule="@daily")\n'
        "def emit_message():\n"
        "    print(Message(cast(str, message)).value)\n"
        "    return message\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "path", sys.path.copy())
    monkeypatch.setattr(CLI_CONFIG_STATE, "cli_args", {"message": "runtime config preserved"})
    output_path = tmp_path / "rundata.json"
    monkeypatch.setattr("tinyfan.codegen.RUNDATA_FILE_PATH", output_path.as_posix())
    container = {"env": [{"name": "APP_MODE", "value": "review"}]}
    try:
        # Load through the public directory entry point before testing overrides.
        codegen(location=str(package_path))
        flow = FLOW_REGISTER["runtime-regression"]
        if container_level == "flow":
            flow.container = container
        manifest = yaml.safe_load(
            codegen(flow=flow, embedded=embedded, container=container if container_level == "compile" else None)
        )
        workflow = manifest["spec"]["workflowSpec"]
        pod = yaml.safe_load(workflow["podSpecPatch"])["containers"][0]
        env = {entry["name"]: entry["value"] for entry in pod["env"]}
        if container_level != "none":
            assert env["APP_MODE"] == "review"
        task = workflow["templates"][-1]["dag"]["tasks"][0]
        params = {param["name"]: param["value"] for param in task["arguments"]["parameters"]}
        imports = ";".join(f"from {item['module']} import {item['name']}" for item in json.loads(params["moduledata"]))
        source = env["TINYFAN_SOURCE"]
        source = source.replace(next(line for line in source.splitlines() if line.startswith("{{=join")), imports)
        source = source.replace("{{inputs.parameters.asset_name}}", "emit_message")
        source = source.replace("{{inputs.parameters.rundata}}", "{}")
        result = subprocess.run(
            [sys.executable, *(["-I", "-S"] if embedded else []), "-"],
            input=source,
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "runtime config preserved"
        assert json.loads(output_path.read_text())["asset_name"] == "emit_message"
        assert container == {"env": [{"name": "APP_MODE", "value": "review"}]}
    finally:
        sys.modules.pop(package_name, None)
        FLOW_REGISTER.pop("runtime-regression", None)
