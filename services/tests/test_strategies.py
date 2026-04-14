from datetime import datetime, timezone
from services.contracts.chunk import Chunk
from services.drop_engine.strategies import (
    SessionStrategy, TimeStrategy, LuckBonusStrategy, CompositeStrategy,
)


def _chunk(duration_sec=1800) -> Chunk:
    return Chunk(
        chunk_id="c1", label="WORK", duration_sec=duration_sec,
        confidence=0.9, started_at=datetime(2026, 4, 14, 9, 0, tzinfo=timezone.utc),
    )


def test_session_strategy_always_one():
    s = SessionStrategy()
    assert s.compute(_chunk(), luck=5) == 1
    assert s.compute(_chunk(duration_sec=10), luck=5) == 1


def test_time_strategy_one_per_interval():
    s = TimeStrategy(interval_sec=900)
    assert s.compute(_chunk(duration_sec=900), luck=0) == 1
    assert s.compute(_chunk(duration_sec=1800), luck=0) == 2
    assert s.compute(_chunk(duration_sec=450), luck=0) == 0


def test_time_strategy_minimum_zero():
    s = TimeStrategy(interval_sec=3600)
    assert s.compute(_chunk(duration_sec=100), luck=0) == 0


def test_luck_bonus_strategy_adds_extra_rolls():
    s = LuckBonusStrategy(luck_per_roll=10)
    assert s.compute(_chunk(), luck=10) == 1
    assert s.compute(_chunk(), luck=5) == 0


def test_composite_strategy_sums():
    s = CompositeStrategy([SessionStrategy(), TimeStrategy(interval_sec=900)])
    assert s.compute(_chunk(duration_sec=1800), luck=0) == 3


def test_composite_strategy_with_luck():
    s = CompositeStrategy([SessionStrategy(), LuckBonusStrategy(luck_per_roll=5)])
    assert s.compute(_chunk(), luck=10) == 3
