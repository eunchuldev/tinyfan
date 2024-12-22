from tinyfan import asset
from .asset import flow


@asset(flow=flow)
def asset2(asset1: str):
    print("asset1 says: " + asset1)
