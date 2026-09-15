from abc import ABC, abstractmethod
from typing import TypeVar

from ..flowrundata import FlowRunData
from ..resources.base import ResourceBase

T = TypeVar("T")


class StoreBase[T, UMeta, StoreIdx](ABC, ResourceBase):
    @staticmethod
    @abstractmethod
    def id() -> str:
        return "tinyfan.basestore"

    @abstractmethod
    def store(
        self,
        value: T,
        rundata: FlowRunData[UMeta, StoreIdx],
    ) -> StoreIdx:
        """should return store index, which is used when retrieve back"""

    @abstractmethod
    def retrieve(
        self,
        index: StoreIdx,
        source_rundata: FlowRunData[UMeta, StoreIdx],
        target_rundata: FlowRunData,
    ) -> T:
        pass
