from tinyfan import Flow, asset

flow: Flow = Flow("test")


@asset(flow=flow, schedule="@daily")
def asset1():
    print("asset1 is executed")
    return "hello"


@asset(flow=flow)
def asset2(asset1: str):
    print("asset1 says: " + asset1)
