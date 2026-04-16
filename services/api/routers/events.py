"""Challenge events API.

GET /events/active  — events whose window contains the current UTC time
GET /events         — all events (past, active, future)
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request

router = APIRouter()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _row_to_dict(row) -> dict:
    return {
        "event_id":   row["event_id"],
        "label":      row["label"],
        "category":   row["category"],
        "multiplier": row["multiplier"],
        "starts_at":  row["starts_at"],
        "ends_at":    row["ends_at"],
    }


@router.get("/active")
def get_active_events(request: Request) -> list[dict]:
    """Return events that are currently in-window."""
    db = request.app.state.db
    now = _now_iso()
    rows = db.execute(
        "SELECT * FROM challenge_events WHERE starts_at <= ? AND ends_at >= ? ORDER BY starts_at",
        (now, now),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


@router.get("")
def get_all_events(request: Request) -> list[dict]:
    """Return all events ordered by start date (past → future)."""
    db = request.app.state.db
    rows = db.execute(
        "SELECT * FROM challenge_events ORDER BY starts_at"
    ).fetchall()
    return [_row_to_dict(r) for r in rows]
