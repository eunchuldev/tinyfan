from datetime import datetime

import tinyfan


@tinyfan.asset(
    schedule="*/1 * * * *",
)
def fast_target() -> str:
    return "world"


@tinyfan.asset(
    schedule="*/2 * * * *",
)
def slow_target() -> str:
    return "earth"

@tinyfan.asset(
    schedule="*/2 * * * *",
)
def slow_greeting(fast_target: list[str], slow_target: str):
    for t in fast_target:
        print("hello " + t)
    print("hello " + slow_target)

@tinyfan.asset()
def greeting(fast_target: str|None, slow_target: str|None):
    if slow_target:
        print("hello " + slow_target)
    if fast_target:
        print("hello " + fast_target)

@tinyfan.asset(
    schedule="*/1 * * * *",
)
def check_variables(ds: str, ts: str, data_interval_start: datetime, data_interval_end: datetime) -> None:
    print(f"ds: {ds}, ts: {ts}")
    print(f"data_interval_start: {data_interval_start}")
    print(f"data_interval_end: {data_interval_end}")
