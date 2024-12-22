import re
from typing import TypeVar

T = TypeVar("T", str, dict, list)


def _jsonpath(data, path):
    for k in path.split("."):
        data = data[k]
    return data


def gotmpl(tmpl: T, data) -> T:
    if isinstance(tmpl, str):
        return re.sub(r"\{\{\s*(.*?)\s*\}\}", lambda match: _jsonpath(data, match.group(1)), tmpl)
    elif isinstance(tmpl, dict):
        return {k: gotmpl(v, data) for k, v in tmpl.items()}
    elif isinstance(tmpl, list):
        return [gotmpl(v, data) for v in tmpl]
    else:
        raise ValueError("First argument must have type of str, dict or list.")
