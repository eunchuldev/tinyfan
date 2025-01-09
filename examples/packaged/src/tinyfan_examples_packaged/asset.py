import tinyfan
from datetime import datetime


@tinyfan.asset(
    schedule="*/1 * * * *", container={"image": "tinyfan-examples-packaged:local", "imagePullPolicy": "Never"}
)
def target() -> str:
    return "world"


@tinyfan.asset(container={"image": "tinyfan-examples-packaged:local", "imagePullPolicy": "Never"})
def greeting(target: str):
    print("hello " + target)


@tinyfan.asset(
    schedule="*/1 * * * *", container={"image": "tinyfan-examples-packaged:local", "imagePullPolicy": "Never"}
)
def check_variables(ds: str, ts: str, data_interval_start: datetime, data_interval_end: datetime) -> None:
    print(f"ds: {ds}, ts: {ts}")
    print(f"data_interval_start: {data_interval_start}")
    print(f"data_interval_end: {data_interval_end}")
