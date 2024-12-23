from typing import TypedDict
from typing import Generic, TypeVar
from .utils.exjson import SerializableDict

UMeta = TypeVar("UMeta", bound=SerializableDict)
StoreIdx = TypeVar("StoreIdx", bound=SerializableDict)


class FlowRunData(TypedDict, Generic[UMeta, StoreIdx], total=False):
    # asset bound data
    metadata: UMeta
    asset_name: str
    flow_name: str
    module_name: str | None

    # runtime data
    ds: str
    ts: str
    parents: dict[str, "FlowRunData"] | None

    # generated data
    store_entry_idx: StoreIdx | None
    # data_interval_start: datetime
