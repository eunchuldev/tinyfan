from typing import TypeVar, Mapping, cast

T = TypeVar("T", bound=Mapping)


def deepmerge(dict1: T, dict2: T, *args: T) -> T:
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
