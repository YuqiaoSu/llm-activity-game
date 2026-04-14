from datetime import datetime, timezone
from services.contracts.chunk import Chunk, SyncState


def test_chunk_requires_fields():
    c = Chunk(
        chunk_id="c_001",
        label="WORK",
        duration_sec=1800,
        confidence=0.92,
        started_at=datetime(2026, 4, 14, 9, 0, tzinfo=timezone.utc),
    )
    assert c.chunk_id == "c_001"
    assert c.label == "WORK"
    assert c.time_of_day is None


def test_chunk_with_time_of_day():
    c = Chunk(
        chunk_id="c_002",
        label="SLEEP",
        duration_sec=28800,
        confidence=0.99,
        started_at=datetime(2026, 4, 14, 23, 0, tzinfo=timezone.utc),
        time_of_day="night",
    )
    assert c.time_of_day == "night"


def test_sync_state_defaults():
    s = SyncState()
    assert s.last_cursor is None
    assert s.last_sync_at is None
    assert s.last_manual_poll_at is None
