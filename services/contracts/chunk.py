from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel


class Chunk(BaseModel):
    """A classified activity window from llm-activity-tracker /v1/chunks."""
    chunk_id: str
    label: str                  # matches Category string values (WORK, GAME, …)
    duration_sec: int
    confidence: float           # 0.0–1.0
    started_at: datetime
    time_of_day: str | None = None  # "morning" | "afternoon" | "evening" | "night"


class SyncState(BaseModel):
    """Persisted cursor into the tracker stream."""
    last_cursor: str | None = None
    last_sync_at: datetime | None = None
    last_manual_poll_at: datetime | None = None
