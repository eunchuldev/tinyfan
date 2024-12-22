import json
import yaml

import jsonpatch
import pytest
from jsonschema.validators import validator_for

from .openapi2jsonschema import openapi2jsonschema

from .helpers import gotmpl as _gotmpl


@pytest.fixture
def assert_manifests():
    __tracebackhide__ = True

    def wrapper(expect: list[dict] | dict, actual: list[dict] | dict):
        res = jsonpatch.JsonPatch.from_diff(
            expect,
            actual,
        )
        res = list(p for p in res if p["op"] != "add")
        if len(res) > 0:
            pytest.fail(json.dumps(res, indent=4))

    return wrapper


@pytest.fixture
def validate_crds(pytestconfig):
    __tracebackhide__ = True

    def wrapper(manifests: str):
        for manifest in yaml.load_all(manifests, yaml.Loader):
            group, version = manifest["apiVersion"].split("/")
            kind = manifest["kind"]
            path = f"{group}/{kind}_{version}.json"
            schema = pytestconfig.cache.get(path, None)
            if schema is None:
                url = f"https://raw.githubusercontent.com/argoproj/argo-workflows/main/manifests/base/crds/full/argoproj.io_{kind.lower()}s.yaml"
                try:
                    res = openapi2jsonschema(url)
                except Exception as e:
                    pytest.fail(f"fail to retreive or convert openapi to jsonschema from `{url}`: {e!s}")
                if res is None:
                    raise Exception(f"openapi2jsonschema return invalid schema for `{kind}`")
                assert kind == res.kind
                assert group == res.fullgroup
                assert version == res.version
                assert res.schema is not None
                pytestconfig.cache.set(path, res.schema)
                schema = res.schema
            klass = validator_for(schema)
            instance = klass(schema)
            instance.validate(manifest)

    return wrapper


@pytest.fixture
def gotmpl():
    __tracebackhide__ = True
    return _gotmpl
