import tinyfan
from tinyfan import ConfigMapKeyRef


class Res(tinyfan.ResourceBase):
    key: ConfigMapKeyRef

    def __init__(self, key: ConfigMapKeyRef):
        self.key = key


class ResContainer(tinyfan.ResourceBase):
    res: Res

    def __init__(self, res: Res):
        self.res = res


flow = tinyfan.Flow(
    name="configs",
    resources={
        "res": Res(ConfigMapKeyRef("tinyfan-config-example", "key")),
        "res2": ResContainer(Res(ConfigMapKeyRef("tinyfan-config-example", "key"))),
    },
)


@tinyfan.asset(
    schedule="*/1 * * * *",
    flow=flow,
)
def trace_res(res: Res):
    print(f"{res.key.get_value()}")


@tinyfan.asset(
    schedule="*/1 * * * *",
    flow=flow,
)
def trace_res2(res2: ResContainer):
    print(f"{res2.res.key.get_value()}")
