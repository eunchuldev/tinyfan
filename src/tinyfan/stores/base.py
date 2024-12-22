from abc import abstractmethod
from typing import Generic, TypeVar
from ..flowrundata import FlowRunData, StoreIdx, UMeta

T = TypeVar("T")


class StoreBase(Generic[T, StoreIdx]):
    @staticmethod
    @abstractmethod
    def id() -> str:
        return "tinyfan.basestore"

    @abstractmethod
    def store(
        self,
        value: T,
        rundata: FlowRunData,
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
