from datetime import datetime
import json
from typing import Mapping, TypeAlias, Sequence


SerializableDict: TypeAlias = (
    Mapping[str, "SerializableDict"] | Sequence["SerializableDict"] | str | int | float | bool | datetime | None
)

DATETIME_ANNOTATION = "__tinyfan_datetime__"


def default(obj):
    if isinstance(obj, datetime):
        return {DATETIME_ANNOTATION: obj.isoformat()}
    else:
        return obj


def object_hook(obj):
    dt = obj.get(DATETIME_ANNOTATION)
    if dt is not None:
        return datetime.fromisoformat(dt)
    else:
        return obj


def dumps(obj: object):
    return json.dumps(obj, default=default)


def loads(obj: str):
    return json.loads(obj, object_hook=object_hook)
