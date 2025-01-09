from abc import abstractmethod, ABC
from typing import Generic, TypeVar
from ..resources.base import ResourceBase
from ..flowrundata import FlowRunData, StoreIdx, UMeta

T = TypeVar("T")


class StoreBase(ABC, ResourceBase, Generic[T, UMeta, StoreIdx]):
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
        pass

    @abstractmethod
    def retrieve(
        self,
        index: StoreIdx,
        source_rundata: FlowRunData[UMeta, StoreIdx],
        target_rundata: FlowRunData,
    ) -> T:
        pass
