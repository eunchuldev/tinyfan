from dataclasses import dataclass, field
from abc import abstractmethod, ABC
import os


@dataclass
class CliConfigState:
    codegen: bool = False
    cli_args: dict[str, str] = field(default_factory=dict)


CLI_CONFIG_STATE = CliConfigState()


def cli_arg(name: str, from_env: str | None = None):
    if CLI_CONFIG_STATE.codegen:
        if name not in CLI_CONFIG_STATE.cli_args:
            if from_env is not None:
                val = os.environ.get(from_env)
                if val is None:
                    raise Exception(f"neither of cli arg `{name}` nor env var `{from_env}` not setted.")
                return val
            raise Exception(f"cli arg `{name}` is not setted.")
        else:
            return CLI_CONFIG_STATE.cli_args[name]
    else:
        return CLI_CONFIG_STATE.cli_args.get(name)


class ConfigValue(ABC):
    @abstractmethod
    def get_value(self) -> str:
        raise Exception(NotImplemented)


class Config(ABC):
    @abstractmethod
    def get(self, name: str) -> str:
        raise Exception(NotImplemented)


@dataclass(frozen=True)
class ConfigMapRef(Config):
    name: str

    def get(self, name: str) -> str:
        val = os.environ.get(name)
        if val is None:
            raise Exception(f"Fail to get `{name}` from ConfigMap `{self.name}`")
        else:
            return val


@dataclass(frozen=True)
class SecretRef(Config):
    name: str

    def get(self, name: str) -> str:
        val = os.environ.get(name)
        if val is None:
            raise Exception(f"Fail to get `{name}` from Secret `{self.name}`")
        else:
            return val


@dataclass(frozen=True)
class ConfigMapKeyRef(ConfigValue):
    name: str
    key: str
    default: str | None = None

    def _env_name(self) -> str:
        return "TINYFAN_CM__" + self.name + "__" + self.key

    def get_value(self) -> str:
        val = os.environ.get(self._env_name(), self.default)
        if val is None:
            raise Exception(f"Fail to get `{self.key}` from ConfigMap `{self.name}`")
        else:
            return val


@dataclass(frozen=True)
class SecretKeyRef(ConfigValue):
    name: str
    key: str
    default: str | None = None

    def _env_name(self) -> str:
        return "TINYFAN_SC__" + self.name + "__" + self.key

    def get_value(self) -> str:
        val = os.environ.get(self._env_name(), self.default)
        if val is None:
            raise Exception(f"Fail to get `{self.key}` from Secret `{self.name}`")
        else:
            return val
