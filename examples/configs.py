import tinyfan
from tinyfan import ConfigMapRef, ConfigMapKeyRef, SecretRef, SecretKeyRef, cli_arg

flow = tinyfan.Flow(
    name="configs",
    configs={
        "constant": "const",
        "configmap": ConfigMapRef("tinyfan-config-example"),
        "configmapkey": ConfigMapKeyRef("tinyfan-config-example", "key"),
        "secret": SecretRef("tinyfan-config-example"),
        "secretkey": SecretKeyRef("tinyfan-config-example", "secretkey"),
        "cliarg": cli_arg("example"),
    },
)


@tinyfan.asset(
    schedule="*/1 * * * *",
    flow=flow,
)
def trace_configs(
    constant: str,
    cliarg: str,
    configmap: ConfigMapRef,
    configmapkey: ConfigMapKeyRef,
    secret: SecretRef,
    secretkey: SecretKeyRef,
):
    print(
        f'{constant} - {cliarg} - {configmap.get("otherkey")} - {configmapkey.get_value()} - {secret.get("othersecretkey")} - {secretkey.get_value()}'
    )
