from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from croniter import croniter

from .flow import Asset


Partition = tuple[Asset, datetime, datetime]


class Expr(ABC):
    def __sub__(self, count: int) -> Shift:
        return Shift(self, count)

    def __getitem__(self, key: int | slice) -> Select:
        return Select(self, key)

    @abstractmethod
    def overlap(self, start: datetime, end: datetime) -> list[Partition]:
        ...

@dataclass
class Shift(Expr):
    source: Expr
    count: int

    def overlap(self, start: datetime, end: datetime) -> list[Partition]:
        result: list[Partition] = []
        for asset, left, right in self.source.overlap(start, end):
            ticks = croniter(asset.schedule, left)
            for _ in range(self.count):
                left, right = ticks.get_prev(datetime), left
            result.append((asset, left, right))
        return result


@dataclass
class Select(Expr):
    source: Expr
    key: int | slice

    def overlap(self, start: datetime, end: datetime) -> list[Partition]:
        parts = self.source.overlap(start, end)
        return parts[self.key] if isinstance(self.key, slice) else [parts[self.key]]
