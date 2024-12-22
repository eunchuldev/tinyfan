import tinyfan


@tinyfan.asset(schedule="*/3 * * * *")
def target() -> str:
    return "world"


@tinyfan.asset()
def greeting(target: str):
    print("hello " + target)
