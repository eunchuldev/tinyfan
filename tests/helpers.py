import re
from typing import TypeVar, cast

T = TypeVar("T", str, dict, list)


def _jsonpath(data, path):
    for k in path.split("."):
        data = data[k]
    return data


def gotmpl[T](tmpl: T, data) -> T:
    if isinstance(tmpl, str):
        return re.sub(r"\{\{\s*(.*?)\s*\}\}", lambda match: _jsonpath(data, match.group(1)), tmpl)
    elif isinstance(tmpl, dict):
        return cast(T, {k: gotmpl(v, data) for k, v in tmpl.items()})
    elif isinstance(tmpl, list):
        return cast(T, [gotmpl(v, data) for v in tmpl])
    else:
        raise TypeError("First argument must have type of str, dict or list.")
