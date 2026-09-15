import base64
import pickle
import zlib
from typing import Any

from .base import FlowRunData, StoreBase


def encode(s: str | bytes) -> str:
    b = s.encode() if isinstance(s, str) else s
    return base64.b64encode(zlib.compress(b, 9)).decode()


def decode(s: str) -> bytes:
    return zlib.decompress(base64.b64decode(s))


class NaiveStore(StoreBase[object, Any, str]):
    @staticmethod
    def id() -> str:
        return "tinyfan.naivestore"

    def store(
        self,
        value: object,
        rundata: FlowRunData,
    ) -> str:
        del rundata
        """should return store index, which is used when retrieve back"""
        return encode(pickle.dumps(value))

    def retrieve(
        self,
        index: str,
        source_rundata: FlowRunData,
        target_rundata: FlowRunData,
    ) -> object:
        del source_rundata, target_rundata
        return pickle.loads(decode(index))
