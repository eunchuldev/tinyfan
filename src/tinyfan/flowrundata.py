import base64
import re
from collections.abc import Mapping
from datetime import datetime
from typing import TypedDict, TypeVar, cast
from zoneinfo import ZoneInfo

from .utils.exjson import dumps, loads

UMeta = TypeVar("UMeta", bound=Mapping | None)
StoreIdx = TypeVar("StoreIdx", bound=Mapping | str | int | None)


class FlowRunData[UMeta, StoreIdx](TypedDict, total=False):
    # asset bound data
    metadata: UMeta
    asset_name: str
    flow_name: str
    module_name: str | None

    # runtime data
    ds: str
    ts: str
    data_interval_start: datetime
    data_interval_end: datetime
    parents: dict[str, "FlowRunData"] | None

    # generated data
    store_entry_idx: StoreIdx | None
    # data_interval_start: datetime


def encode_rundata(rundata: FlowRunData) -> str:
    """Keep runtime metadata opaque while Argo substitutes workflow parameters."""
    return base64.b64encode(dumps(rundata).encode("utf-8")).decode("ascii")


def load_rundata(text: str) -> FlowRunData:
    """Resolve the scheduled interval and decode the input envelope's parents."""
    rundata = loads(text)
    if not isinstance(rundata, dict):
        raise TypeError("Tinyfan runtime data must be a JSON object")
    if "schedule" in rundata:
        from croniter import croniter

        schedule = rundata.pop("schedule")
        timezone = ZoneInfo(rundata.pop("timezone"))
        if "scheduled_time_b64" in rundata:
            scheduled_time = base64.b64decode(rundata.pop("scheduled_time_b64"), validate=True).decode("utf-8")
        else:
            scheduled_time = rundata.pop("scheduled_time")
        # The alpha backfill CLI emits Go Time.String(), including a zone label.
        # Its numeric offset, not the possibly ambiguous label, identifies the instant.
        backfill_time = re.fullmatch(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?) ([+-]\d{4}) \S+", scheduled_time)
        if backfill_time:
            scheduled_time = backfill_time[1] + backfill_time[2]
        end = datetime.fromisoformat(scheduled_time)
        if end.tzinfo is None:
            raise ValueError("Tinyfan scheduled_time must include a UTC offset")
        end = end.astimezone(timezone)
        cron = croniter(schedule, end)
        start = cron.get_prev(datetime)
        # Croniter normalizes missing DST times; Argo skips those schedule hits.
        # Match the local clock without DST normalization to reject shifted hits.
        while not croniter.match(schedule, start.replace(tzinfo=None)):
            start = cron.get_prev(datetime)
        rundata.update(
            ds=start.date().isoformat(),
            ts=start.isoformat(),
            data_interval_start=start,
            data_interval_end=end,
        )
    parents = rundata.get("parents")
    if parents is not None:
        if not isinstance(parents, dict):
            raise TypeError("Tinyfan runtime parents must be a JSON object")
        for name, value in parents.items():
            if not isinstance(value, str):
                raise TypeError(f"Tinyfan parent `{name}` must be base64-encoded JSON")
            parent = loads(base64.b64decode(value, validate=True).decode("utf-8"))
            if not isinstance(parent, dict):
                raise TypeError(f"Tinyfan parent `{name}` must decode to a JSON object")
            parents[name] = parent
    return cast(FlowRunData, rundata)
