from tinyfan import Flow, asset

flow: Flow = Flow("test")


@asset(flow=flow, schedule="@daily")
def asset1():
    print("asset1 is executed")
    return "hello"
