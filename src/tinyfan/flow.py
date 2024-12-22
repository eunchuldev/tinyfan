import inspect
from .stores.base import StoreBase
from .stores.naive import NaiveStore
from .flowrundata import FlowRunData, StoreIdx, UMeta
from dataclasses import dataclass, field
from typing import Callable, Any, Generic, TypeVar, Mapping

FLOW_CATALOG = {}

Res = TypeVar("Res", bound=Mapping)
Ret = TypeVar("Ret", bound=Mapping)


@dataclass
class Flow(Generic[Res]):
    name: str
    image: str | None = None
    tz: str = "UTC"
    assets: dict[str, "Asset[Any, Res, Any, Any]"] = field(default_factory=dict)
    resources: Res | None = None
    store: StoreBase = field(default_factory=NaiveStore)

    def __post_init__(self):
        FLOW_CATALOG[self.name] = self


DEFAULT_FLOW: Flow[Any] = Flow("tinyfan", image="python:alpine")


@dataclass
class Asset(Generic[Ret, Res, UMeta, StoreIdx]):
    flow: Flow[Res]
    func: Callable[..., Ret]
    store: StoreBase[Ret, StoreIdx]
    image: str | None = None
    schedule: str | None = None
    tz: str | None = None
    metadata: UMeta | None = None
    depends: str | None = None
    name: str = field(init=False)

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
        params = {k: v for k, v in rundata.items() if k in func_param_names}
        if self.flow.resources:
            for k, v in self.flow.resources:
                if k in func_param_names:
                    params[k] = v

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


def asset(
    flow: Flow = DEFAULT_FLOW,
    schedule: str | None = None,
    depends: str | None = None,
    store: StoreBase | None = None,
):
    class wrapper(Generic[Ret]):
        func: Callable[..., Ret]
        asset: Asset

        def __init__(self, func: Callable[..., Ret]):
            self.func = func
            self.asset = Asset(flow, func=func, depends=depends, schedule=schedule, store=store or flow.store)

        def __call__(self, *args, **kwargs) -> Ret:
            res = self.func(*args, **kwargs)
            return res

    return wrapper
