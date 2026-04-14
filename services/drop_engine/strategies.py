from __future__ import annotations
from abc import ABC, abstractmethod
from services.contracts.chunk import Chunk


class RollStrategy(ABC):
    """Abstract roll strategy. Returns number of lottery rolls for a chunk."""

    @abstractmethod
    def compute(self, chunk: Chunk, luck: int) -> int: ...


class SessionStrategy(RollStrategy):
    """Always 1 roll per qualifying chunk, regardless of duration."""

    def compute(self, chunk: Chunk, luck: int) -> int:
        return 1


class TimeStrategy(RollStrategy):
    """1 roll per `interval_sec` of chunk duration (integer division)."""

    def __init__(self, interval_sec: int = 900) -> None:
        self.interval_sec = interval_sec

    def compute(self, chunk: Chunk, luck: int) -> int:
        return chunk.duration_sec // self.interval_sec


class LuckBonusStrategy(RollStrategy):
    """Extra rolls = luck // luck_per_roll."""

    def __init__(self, luck_per_roll: int = 10) -> None:
        self.luck_per_roll = luck_per_roll

    def compute(self, chunk: Chunk, luck: int) -> int:
        return luck // self.luck_per_roll


class CompositeStrategy(RollStrategy):
    """Sum rolls from multiple strategies."""

    def __init__(self, strategies: list[RollStrategy]) -> None:
        self.strategies = strategies

    def compute(self, chunk: Chunk, luck: int) -> int:
        return sum(s.compute(chunk, luck) for s in self.strategies)
