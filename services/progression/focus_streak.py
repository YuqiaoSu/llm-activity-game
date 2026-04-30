"""Focus streak tracking.

A focus session = a poll that contained ≥ 1 WORK or LEARN chunk.
The streak increments once per calendar day (idempotent within a day),
resets to 1 if the last focus was more than 1 day ago.
"""
from __future__ import annotations
import sqlite3
from datetime import date

_FOCUS_LABELS = {"WORK", "LEARN"}
_MILESTONE_AT = 5  # reward badge threshold


def update_focus_streak(db: sqlite3.Connection, had_focus_session: bool) -> None:
    """Update focus_streak for today based on whether this poll had focus chunks.

    Idempotent within a calendar day — calling it twice on the same day has no
    additional effect. Caller must commit after this returns.
    """
    row = db.execute(
        "SELECT focus_streak, last_focus_date FROM streak_state WHERE player_id='default'"
    ).fetchone()
    if row is None:
        return

    today = date.today().isoformat()
    last_date: str | None = row["last_focus_date"]
    current: int = int(row["focus_streak"]) if row["focus_streak"] is not None else 0

    if last_date == today:
        # Already processed today — idempotent
        return

    if not had_focus_session:
        # Non-focus poll: streak resets only if a day was skipped
        if last_date is not None:
            last = date.fromisoformat(last_date)
            if (date.today() - last).days > 1:
                db.execute(
                    "UPDATE streak_state SET focus_streak=0, last_focus_date=NULL"
                    " WHERE player_id='default'"
                )
        return

    # Focus session this poll
    if last_date is None:
        new_streak = 1
    else:
        last = date.fromisoformat(last_date)
        gap = (date.today() - last).days
        if gap == 1:
            new_streak = current + 1
        elif gap == 0:
            return  # already counted today
        else:
            new_streak = 1  # streak broken

    db.execute(
        "UPDATE streak_state SET focus_streak=?, last_focus_date=? WHERE player_id='default'",
        (new_streak, today),
    )


def get_focus_streak(db: sqlite3.Connection) -> dict:
    """Return current focus streak state."""
    row = db.execute(
        "SELECT focus_streak, last_focus_date FROM streak_state WHERE player_id='default'"
    ).fetchone()
    streak: int = int(row["focus_streak"]) if row and row["focus_streak"] else 0
    last: str | None = row["last_focus_date"] if row else None
    next_reward_at: int | None = None
    if streak < _MILESTONE_AT:
        next_reward_at = _MILESTONE_AT
    return {
        "focus_streak":    streak,
        "last_focus_date": last,
        "next_reward_at":  next_reward_at,
    }


def has_focus_chunks(chunks: list[dict]) -> bool:
    """Return True if any chunk in the list has a WORK or LEARN label."""
    return any(c.get("label", "").upper() in _FOCUS_LABELS for c in chunks)
