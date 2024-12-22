from datetime import datetime
import json
from typing import Mapping, TypeAlias, Sequence


SerializableDict: TypeAlias = (
    Mapping[str, "SerializableDict"] | Sequence["SerializableDict"] | str | int | float | bool | datetime | None
)


def default(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    else:
        return obj


def object_hook(obj):
    try:
        return datetime.fromisoformat(obj)
    except ValueError:
        return obj


def dumps(obj: object):
    return json.dumps(obj, default=default)


def loads(obj: str):
    return json.loads(obj, object_hook=object_hook)
