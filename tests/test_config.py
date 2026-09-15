import os
from collections.abc import Generator
from unittest import mock

import pytest
import yaml

from tinyfan import ConfigMapKeyRef, ConfigMapRef, Flow, ResourceBase, SecretKeyRef, SecretRef, asset
from tinyfan.codegen import codegen
from tinyfan.flow import FLOW_REGISTER
from tinyfan.stores.gcs_pickle import GcsPickleStore


# type: ignore
@pytest.fixture()
def sample_flow() -> Generator:
    class Resource(ResourceBase):
        cm = ConfigMapRef("cm")
        cm_key = ConfigMapKeyRef("cm", "key")
        cm_default = ConfigMapKeyRef("cm", "non_key", "default")
        sec = SecretRef("secret")
        sec_key = SecretKeyRef("secret", "key")
        sec_default = SecretKeyRef("secret", "non_key", "default")

    flow: Flow = Flow(
        "test",
        resources={
            "res": Resource(),
        },
    )

    @asset(flow=flow, schedule="@daily")
    def test_asset(res: Resource):  # type: ignore
        return (
            res.cm.get("key"),
            res.cm_key.get_value(),
            res.cm_default.get_value(),
            res.sec.get("key"),
            res.sec_key.get_value(),
            res.sec_default.get_value(),
        )

    yield flow
    FLOW_REGISTER.clear()


# HACK IT: skip it at this stage. too tired.
def test_resource_config_codgen(validate_crds, sample_flow):
    res = codegen(flow=sample_flow)
    validate_crds(res)


def test_resource_config_run(sample_flow: Flow):
    env = {
        "TINYFAN_CM__cm__key": "cmkey",
        "TINYFAN_SC__secret__key": "sekey",
        "key": "key",
    }
    with mock.patch.dict(os.environ, env):
        _ = codegen(flow=sample_flow)
        asset = next(iter(sample_flow.assets.values()))
        actual, _ = asset.run()
        expected = ("key", "cmkey", "default", "key", "sekey", "default")
        assert actual == expected


def test_store_config_refs():
    flow = Flow("store-refs", store=GcsPickleStore(ConfigMapKeyRef("storage", "bucket")))

    @asset(flow=flow, schedule="@daily")
    def source():
        return 1

    @asset(flow=flow, store=GcsPickleStore(SecretKeyRef("private-storage", "bucket")))
    def consumer(source):
        return source

    try:
        manifest = yaml.safe_load(codegen(flow=flow))
        templates = {item["name"]: item for item in manifest["spec"]["workflowSpec"]["templates"]}
        source_env = {item["name"]: item["valueFrom"] for item in templates["source"]["script"]["env"]}
        consumer_env = {item["name"]: item["valueFrom"] for item in templates["consumer"]["script"]["env"]}
        assert source_env["TINYFAN_CM__storage__bucket"] == {"configMapKeyRef": {"name": "storage", "key": "bucket"}}
        assert consumer_env == {
            **source_env,
            "TINYFAN_SC__private-storage__bucket": {"secretKeyRef": {"name": "private-storage", "key": "bucket"}},
        }
    finally:
        FLOW_REGISTER.pop(flow.name, None)
