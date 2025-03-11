from tinyfan import Flow, asset, ResourceBase, ConfigMapRef, ConfigMapKeyRef, SecretRef, SecretKeyRef
from tinyfan.flow import FLOW_REGISTER
from tinyfan.codegen import codegen
from typing import Generator
from unittest import mock
import pytest
import os


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
        asset = list(sample_flow.assets.values())[0]
        actual, _ = asset.run()
        expected = ("key", "cmkey", "default", "key", "sekey", "default")
        assert actual == expected
