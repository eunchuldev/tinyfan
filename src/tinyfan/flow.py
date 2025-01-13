import inspect
from .stores.base import StoreBase
from .stores.naive import NaiveStore
from .flowrundata import FlowRunData, StoreIdx, UMeta
from dataclasses import dataclass, field
from typing import Callable, Any, Generic, TypeVar
from .resources.base import ResourceBase
from .argo_typing import ScriptTemplate
from .config import Config, ConfigValue

FLOW_REGISTER = {}

Ret = TypeVar("Ret")

DEFAULT_IMAGE = "python:alpine"


@dataclass
class Flow:
    name: str
    tz: str = "UTC"
    assets: dict[str, "Asset[Any, Any, Any]"] = field(default_factory=dict)
    resources: dict[str, ResourceBase] | None = None
    container: ScriptTemplate | None = None
    serviceAccountName: str | None = None
    store: StoreBase = field(default_factory=NaiveStore)
    configs: dict[str, Config | ConfigValue | str | None] = field(default_factory=dict)

    def __post_init__(self):
        FLOW_REGISTER[self.name] = self


DEFAULT_FLOW: Flow = Flow(
    "tinyfan",
    container={
        "image": DEFAULT_IMAGE,
    },
)


@dataclass
class Asset(Generic[Ret, UMeta, StoreIdx]):
    flow: Flow
    func: Callable[..., Ret]
    store: StoreBase[Ret, UMeta, StoreIdx]
    schedule: str | None = None
    tz: str | None = None
    metadata: UMeta | None = None
    depends: str | None = None
    name: str = field(init=False)
    container: ScriptTemplate | None = None
    serviceAccountName: str | None = None

    def __post_init__(self):
        self.name = self.func.__name__
        self.flow.assets[self.name] = self

    def run(self, rundata: FlowRunData[UMeta, StoreIdx] | None = None) -> tuple[Ret, FlowRunData[UMeta, StoreIdx]]:
        rundata = rundata or {}
        sigs = inspect.signature(self.func)
        func_param_names = list(sigs.parameters.keys())
        if self.metadata is not None:
            rundata["metadata"] = self.metadata
        rundata["asset_name"] = self.name
        rundata["flow_name"] = self.flow.name
        mod = inspect.getmodule(self.func)
        if mod and mod.__name__:
            rundata["module_name"] = mod.__name__
        params: dict[str, object] = {k: v for k, v in rundata.items() if k in func_param_names}
        if self.flow.resources:
            for k, v in self.flow.resources.items():
                if k in func_param_names:
                    params[k] = v
        if self.flow.configs:
            for k2, v2 in self.flow.configs.items():
                if k2 in func_param_names:
                    params[k2] = v2

        parent_flowrundatas: dict[str, FlowRunData] = rundata.get("parents") or {}
        for name, prundata in parent_flowrundatas.items():
            parent = self.flow.assets[name]
            index = prundata.get("store_entry_idx", None)
            data = parent.store.retrieve(index, source_rundata=prundata, target_rundata=rundata)
            if name in func_param_names:
                params[name] = data
        ret = self.func(**params)
        store_entry_idx = self.store.store(ret, rundata)
        rundata["store_entry_idx"] = store_entry_idx
        if "parents" in rundata:
            del rundata["parents"]
        return (ret, rundata)


class AssetFunc(Generic[Ret, UMeta, StoreIdx]):
    func: Callable[..., Ret]
    asset: Asset[Ret, UMeta, StoreIdx]

    def __init__(self, func: Callable[..., Ret], asset: Asset[Ret, UMeta, StoreIdx]):
        self.func = func
        self.asset = asset

    def __call__(self, *args, **kwargs) -> Ret:
        res = self.func(*args, **kwargs)
        return res


def asset(
    flow: Flow = DEFAULT_FLOW,
    schedule: str | None = None,
    depends: str | None = None,
    store: StoreBase[Ret, UMeta, StoreIdx] | None = None,
    tz: str | None = None,
    metadata: UMeta | None = None,
    container: ScriptTemplate | None = None,
    serviceAccountName: str | None = None,
) -> Callable[..., AssetFunc[Ret, UMeta, StoreIdx]]:
    def wrapper(func: Callable[..., Ret]) -> AssetFunc[Ret, UMeta, StoreIdx]:
        asset = Asset[Ret, UMeta, StoreIdx](
            flow,
            func=func,
            depends=depends,
            schedule=schedule,
            store=store or flow.store,
            tz=tz or flow.tz,
            metadata=metadata,
            container=container,
            serviceAccountName=serviceAccountName,
        )
        return AssetFunc(func, asset)

    return wrapper
