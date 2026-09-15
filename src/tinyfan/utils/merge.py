from collections.abc import Mapping
from typing import TypeVar, cast

T = TypeVar("T", bound=Mapping)


def deepmerge[T](dict1: T, dict2: T, *args: T) -> T:
    if not isinstance(dict1, dict) or not isinstance(dict2, dict):
        return dict2
    for k in dict2:
        if k in dict1:
            dict1[k] = deepmerge(dict1[k], dict2[k])
        else:
            dict1[k] = dict2[k]
    dict1 = cast(T, dict1)
    for arg in args:
        deepmerge(dict1, arg)
    return dict1


def dropnone(d: dict) -> dict:
    dropping = []
    for k, v in d.items():
        if v is None:
            dropping.append(k)
    for k in dropping:
        del d[k]
    return d
