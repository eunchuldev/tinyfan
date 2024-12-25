from typing import TypedDict, NotRequired


class ExecAction(TypedDict):
    command: list[str]


class SecretKeySelector(TypedDict):
    key: str
    name: str
    optional: NotRequired[bool]


class HTTPHeaderSource(TypedDict):
    secretKeyRef: SecretKeySelector


class HTTPHeader(TypedDict):
    name: str
    value: NotRequired[str]
    valueFrom: NotRequired[HTTPHeaderSource]


class HTTPGetAction(TypedDict):
    host: str
    httpHeaders: NotRequired[list[HTTPHeader]]
    path: NotRequired[str]
    port: NotRequired[str | int]
    scheme: NotRequired[str]


class TCPSocketAction(TypedDict):
    host: str
    port: str | int


class SleepAction(TypedDict):
    seconds: int


class LifecycleHandler(TypedDict, total=False):
    exec: ExecAction
    httpGet: HTTPGetAction
    sleep: SleepAction
    tcpSocket: TCPSocketAction


class GRPCAction(TypedDict):
    port: int
    service: str


class Probe(TypedDict, total=False):
    exec: ExecAction
    failureThreshold: int
    grpc: GRPCAction
    httpGet: HTTPGetAction
    initialDelaySeconds: int
    periodSeconds: int
    successThreshold: int
    tcpSocket: TCPSocketAction
    terminationGracePeriodSeconds: int
    timeoutSeconds: int


class ConfigMapKeySelector(TypedDict):
    key: str
    name: str
    optional: NotRequired[bool]


class ObjectFieldSelector(TypedDict):
    apiVersion: str
    fieldPath: str


class ResourceFieldSelector(TypedDict):
    containerName: str
    divisor: str
    resource: str


class EnvVarSource(TypedDict, total=False):
    configMapKeyRef: ConfigMapKeySelector
    fieldRef: ObjectFieldSelector
    resourceFieldRef: ResourceFieldSelector
    secretKeyRef: SecretKeySelector


class EnvVar(TypedDict):
    name: str
    value: NotRequired[str]
    valueFrom: NotRequired[EnvVarSource]


class Lifecycle(TypedDict, total=False):
    postStart: LifecycleHandler
    preStop: LifecycleHandler


class ContainerResizePolicy(TypedDict):
    resourceName: str
    restartPolicy: str


class ResourceQuantity(TypedDict, total=False):
    memory: str
    cpu: str


class ResourceClaim(TypedDict):
    name: str
    request: ResourceQuantity


class ResourceRequirements(TypedDict, total=False):
    claims: list[ResourceClaim]
    limits: ResourceQuantity
    requests: ResourceQuantity


class AppArmorProfile(TypedDict, total=False):
    localhostProfile: str
    type: str


class Capabilities(TypedDict, total=False):
    add: list[str]
    drop: list[str]


class SELinuxOptions(TypedDict, total=False):
    level: str
    role: str
    type: str
    user: str


class SeccompProfile(TypedDict, total=False):
    localhostProfile: str
    type: str


class WindowOptions(TypedDict, total=False):
    gmsaCredentialSpec: str
    gmsaCredentialSpecName: str
    hostProcess: bool
    runAsUserName: str


class SecurityContext(TypedDict, total=False):
    allowPrivilegeEscalation: bool
    appArmorProfile: AppArmorProfile
    capabilities: Capabilities
    privileged: bool
    procMount: str
    readOnlyRootFilesystem: bool
    runAsGroup: int
    runAsNonRoot: bool
    runAsUser: int
    seLinuxOptions: SELinuxOptions
    seccompProfile: SeccompProfile
    windowOptions: WindowOptions


class VolumeDevice(TypedDict):
    devicePath: str
    name: str


class VolumeMount(TypedDict, total=False):
    mounstPath: str
    mountPropagation: str
    name: str
    readOnly: bool
    recursiveReadOnly: str
    subPath: str
    subPathExpr: str


# Ref: https://argo-workflows.readthedocs.io/en/latest/fields/#scripttemplate
class ScriptTemplate(TypedDict, total=False):
    args: list[str]
    command: list[str]
    env: list[EnvVar]
    envFrom: list[EnvVar]
    image: str
    imagePullPolicy: str
    lifecycle: Lifecycle
    livenessProbe: Probe
    readinessProbe: Probe
    resizePolicy: list[ContainerResizePolicy]
    resources: ResourceRequirements
    restartPolicy: str
    securityContext: SecurityContext
    statusProbe: Probe
    stdin: bool
    stdinOnce: bool
    terminationMessagePath: str
    terminationMessagePolicy: str
    tty: bool
    volumeDevices: list[VolumeDevice]
    volumeMounts: list[VolumeMount]
    workingDir: str
