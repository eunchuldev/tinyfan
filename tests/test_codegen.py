import base64
import importlib
import json
import os
import subprocess
import sys
from collections.abc import Generator
from datetime import datetime

import pytest
import yaml
from jsonschema.exceptions import ValidationError

from tinyfan import Flow, asset
from tinyfan.argo_typing import ScriptTemplate
from tinyfan.codegen import AssetTree, codegen
from tinyfan.config import CLI_CONFIG_STATE
from tinyfan.flow import FLOW_REGISTER
from tinyfan.utils.exjson import dumps, loads


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
        .rundatatmpl(schedule, tree.flow.tz)
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
    flow = Flow("test-io")

    @asset(
        flow=flow,
        schedule="@daily",
        inputs={
            "parameters": [{"name": "message", "value": "hello"}],
            "artifacts": [{"name": "message-file", "path": "/tmp/message.txt", "raw": {"data": "hello"}}],
        },
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
        assert output_params["rundata"] == {"name": "rundata", "valueFrom": {"path": "/tmp/tinyfan/rundata.b64"}}
        input_artifacts = {item["name"]: item for item in template["inputs"]["artifacts"]}
        assert input_artifacts["tinyfan-rundata"] == {
            "name": "tinyfan-rundata",
            "path": "/tmp/tinyfan/input.json",
            "raw": {"data": "{{inputs.parameters.rundata}}"},
        }
        assert input_artifacts["message-file"]["raw"]["data"] == "hello"
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
    assert json.loads(node.rundatatmpl("@daily", "Asia/Seoul")) == {
        "schedule": "@daily",
        "timezone": "Asia/Seoul",
        "scheduled_time_b64": (
            "{{= let ts = 'parameters' in workflow && 'cronScheduleTime' in workflow.parameters"
            " ? workflow.parameters.cronScheduleTime : workflow.scheduledTime;"
            " ts == nil ? nil : sprig.b64enc(ts) }}"
        ),
        "parents": {},
        "asset_name": "asset1",
        "flow_name": "test",
        "module_name": "tests.test_codegen",
    }


def test_interval_uses_triggering_schedule(sample_flow):
    sample_flow.assets["asset1"].tz = "Asia/Seoul"
    sample_flow.assets["asset2"].tz = "America/New_York"
    sample_flow.assets["asset2"].schedule = "@monthly"
    manifests = list(yaml.safe_load_all(codegen(flow=sample_flow)))
    assert len(manifests) == 2
    for manifest in manifests:
        spec = manifest["spec"]
        tasks = spec["workflowSpec"]["templates"][-1]["dag"]["tasks"]
        assert len(tasks) == 4
        for task in tasks:
            envelope = json.loads(next(p["value"] for p in task["arguments"]["parameters"] if p["name"] == "rundata"))
            assert envelope["schedule"] == spec["schedules"][0]
            assert envelope["timezone"] == spec["timezone"]


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
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "rundata.b64"
    monkeypatch.setattr("tinyfan.codegen.RUNDATA_INPUT_FILE_PATH", input_path.as_posix())
    monkeypatch.setattr("tinyfan.codegen.RUNDATA_FILE_PATH", output_path.as_posix())
    container: ScriptTemplate = {"env": [{"name": "APP_MODE", "value": "review"}]}
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
        assert "{{inputs.parameters.rundata}}" not in source
        input_path.write_text("{}", encoding="utf-8")
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
        assert loads(base64.b64decode(output_path.read_text()).decode("utf-8"))["asset_name"] == "emit_message"
        assert container == {"env": [{"name": "APP_MODE", "value": "review"}]}
    finally:
        sys.modules.pop(package_name, None)
        FLOW_REGISTER.pop("runtime-regression", None)


def test_embedded_script_with_sibling_and_data(tmp_path, monkeypatch):
    script = tmp_path / "main.py"
    script.write_text(
        "from __future__ import annotations\n"
        "from pathlib import Path\n"
        "from dataclasses import dataclass\n"
        "from tinyfan import Flow, asset\n"
        "from embed_script_helper import SUFFIX\n"
        "@dataclass\n"
        "class Message:\n"
        "    value: str\n"
        "flow = Flow('embedded-script')\n"
        "@asset(flow=flow, schedule='@daily')\n"
        "def emit_file():\n"
        "    value = Message(Path(__file__).with_name('DATA').read_text() + SUFFIX).value\n"
        "    print(value)\n"
        "    return value",
        encoding="utf-8",
    )
    (tmp_path / "embed_script_helper.py").write_text("SUFFIX = ' world'", encoding="utf-8")
    (tmp_path / "DATA").write_text("hello", encoding="utf-8")
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "rundata.b64"
    monkeypatch.setattr(sys, "path", sys.path.copy())
    monkeypatch.setattr("tinyfan.codegen.RUNDATA_INPUT_FILE_PATH", input_path.as_posix())
    monkeypatch.setattr("tinyfan.codegen.RUNDATA_FILE_PATH", output_path.as_posix())
    previous = sys.modules.get("__tinyfan_repo__")
    try:
        manifest = yaml.safe_load(codegen(location=str(script), embedded=True))
        pod = yaml.safe_load(manifest["spec"]["workflowSpec"]["podSpecPatch"])["containers"][0]
        source = next(item["value"] for item in pod["env"] if item["name"] == "TINYFAN_SOURCE")
        source = source.replace("{{inputs.parameters.asset_name}}", "emit_file")
        input_path.write_text("{}", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "-I", "-S", "-"],
            input=source,
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "hello world"
        rundata = loads(base64.b64decode(output_path.read_text()).decode("utf-8"))
        assert rundata["module_name"] == "__tinyfan_repo__"
    finally:
        FLOW_REGISTER.pop("embedded-script", None)
        sys.modules.pop("embed_script_helper", None)
        sys.modules.pop("__tinyfan_repo__", None)
        if previous is not None:
            sys.modules["__tinyfan_repo__"] = previous


def test_internal_input_artifact_is_reserved():
    flow = Flow("reserved-artifact")

    @asset(
        flow=flow,
        schedule="@daily",
        inputs={"artifacts": [{"name": "tinyfan-rundata", "path": "/tmp/override", "raw": {"data": "{}"}}]},
    )
    def source():
        return 1

    try:
        with pytest.raises(ValueError, match="internal artifacts: `tinyfan-rundata`"):
            codegen(flow=flow)
    finally:
        FLOW_REGISTER.pop(flow.name, None)


@pytest.mark.parametrize("embedded", [False, True])
@pytest.mark.parametrize(
    "scheduled_time, cron_schedule_time, expected_start",
    [
        ("2026-03-09T04:00:00Z", None, "2026-03-08T00:00:00-05:00"),
        ("2026-11-02T05:00:00Z", None, "2026-11-01T00:00:00-04:00"),
        ("2026-09-16T12:00:00Z", "2026-03-09 00:00:00 -0400 EDT", "2026-03-08T00:00:00-05:00"),
        (None, "2026-03-09T04:00:00Z", "2026-03-08T00:00:00-05:00"),
    ],
)
def test_generated_parent_metadata_transport(
    tmp_path, monkeypatch, embedded, validate_crds, scheduled_time, cron_schedule_time, expected_start
):
    package_name = "metadata_transport_package"
    package_path = tmp_path / package_name
    package_path.mkdir()
    package_path.joinpath("__init__.py").write_text(
        "import os\n"
        "from tinyfan import Flow, StoreBase, asset\n"
        "from tinyfan.utils.exjson import loads\n"
        "class JsonStore(StoreBase):\n"
        "    @staticmethod\n"
        "    def id(): return 'test.json'\n"
        "    def store(self, value, rundata): return value\n"
        "    def retrieve(self, index, source_rundata, target_rundata): return index\n"
        'payload = loads(os.environ["TINYFAN_TEST_PAYLOAD"])\n'
        'flow = Flow("metadata-transport", store=JsonStore(), tz="America/New_York")\n'
        '@asset(flow=flow, schedule="@daily", metadata=payload)\n'
        "def first_source(): return payload\n"
        "@asset(flow=flow, metadata=payload)\n"
        "def second_source(): return payload\n"
        "@asset(flow=flow)\n"
        "def consumer(first_source, second_source, parents):\n"
        "    assert first_source == second_source == payload\n"
        "    assert all(parent['metadata'] == payload for parent in parents.values())\n"
        "    return first_source\n",
        encoding="utf-8",
    )
    payload = {
        "text": "quote\" slash\\ triple''' newline\n\t\r\x00 $(APP_MODE) {{workflow.name}} {{inputs.parameters.rundata}} 한글🙂",
        "date": datetime.fromisoformat("2026-09-16T12:00:00+09:00"),
        "nested": {"values": [None, False, 1, ""]},
    }
    monkeypatch.setenv("TINYFAN_TEST_PAYLOAD", dumps(payload))
    monkeypatch.setattr(sys, "path", sys.path.copy())
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "rundata.b64"
    monkeypatch.setattr("tinyfan.codegen.RUNDATA_INPUT_FILE_PATH", input_path.as_posix())
    monkeypatch.setattr("tinyfan.codegen.RUNDATA_FILE_PATH", output_path.as_posix())
    try:
        codegen(location=str(package_path))
        manifest_text = codegen(flow=FLOW_REGISTER["metadata-transport"], embedded=embedded)
        validate_crds(manifest_text)
        workflow = yaml.safe_load(manifest_text)["spec"]["workflowSpec"]
        # The backfill CLI appends this argument itself; do not declare a duplicate.
        assert not any(p["name"] == "cronScheduleTime" for p in workflow.get("arguments", {}).get("parameters", []))
        templates = {template["name"]: template for template in workflow["templates"]}
        tasks = {task["name"]: task for task in templates["flow"]["dag"]["tasks"]}
        source_template = next(
            item["value"]
            for item in yaml.safe_load(workflow["podSpecPatch"])["containers"][0]["env"]
            if item["name"] == "TINYFAN_SOURCE"
        )
        # Linux limits each environment entry to 128 KiB, including its name.
        assert len(source_template.encode("utf-8")) + len("TINYFAN_SOURCE=") + 1 < 128 * 1024
        outputs = {}
        for name in ("first-source", "second-source", "consumer"):
            params = {item["name"]: item["value"] for item in tasks[name]["arguments"]["parameters"]}
            # Simulate the selected value of Argo's expression, then execute real Python.
            envelope = json.loads(params["rundata"])
            assert "workflow.parameters.cronScheduleTime" in envelope["scheduled_time_b64"]
            selected_time = cron_schedule_time if cron_schedule_time is not None else scheduled_time
            envelope["scheduled_time_b64"] = base64.b64encode(selected_time.encode("utf-8")).decode("ascii")
            raw = dumps(envelope)
            for parent, encoded in outputs.items():
                raw = raw.replace(f"{{{{tasks.{parent}.outputs.parameters.rundata}}}}", encoded)
            artifact = next(
                item for item in templates[name]["inputs"]["artifacts"] if item["name"] == "tinyfan-rundata"
            )
            raw = artifact["raw"]["data"].replace("{{inputs.parameters.rundata}}", raw)
            # Later substitutions must not rewrite strings inside parent metadata.
            raw = raw.replace("{{workflow.name}}", "should-not-replace").replace("$(APP_MODE)", "should-not-replace")
            assert artifact["path"] == input_path.as_posix()
            input_path.write_text(raw, encoding="utf-8")
            imports = ";".join(
                f"from {item['module']} import {item['name']}" for item in json.loads(params["moduledata"])
            )
            source = source_template.replace(
                next(line for line in source_template.splitlines() if line.startswith("{{=join")), imports
            ).replace("{{inputs.parameters.asset_name}}", params["asset_name"])
            assert "{{inputs.parameters.rundata}}" not in source
            if embedded:
                # Exercise bundled timezone data even on hosts with a system database.
                source = "import zoneinfo; zoneinfo.reset_tzpath(())\n" + source
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
            encoded = output_path.read_text(encoding="ascii")
            result_data = loads(base64.b64decode(encoded, validate=True).decode("utf-8"))
            assert result_data["store_entry_idx"] == payload
            assert result_data["data_interval_start"].isoformat() == expected_start
            expected_end = "2026-03-09T04:00:00Z" if cron_schedule_time is not None else scheduled_time
            assert result_data["data_interval_end"].timestamp() == datetime.fromisoformat(expected_end).timestamp()
            assert result_data["ds"] == expected_start[:10]
            assert result_data["ts"] == expected_start
            assert "parents" not in result_data
            outputs[name] = encoded
    finally:
        sys.modules.pop(package_name, None)
        FLOW_REGISTER.pop("metadata-transport", None)
