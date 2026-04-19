"""Daily activity streak tracking.

Rules:
- A "day" is the UTC calendar date of the chunk being processed.
- First ever XP: streak becomes 1.
- XP on the same date as last_active_date: no change (idempotent).
- XP on the date immediately after last_active_date: streak += 1.
- XP with a gap > 1 day: streak resets to 1.
- longest_streak is updated whenever current_streak surpasses it.
"""
from __future__ import annotations
import sqlite3
from datetime import date, timedelta


def _yesterday(d: date) -> date:
    return d - timedelta(days=1)


def consume_streak_freeze(conn: sqlite3.Connection) -> bool:
    """Consume one streak freeze charge if available.

    Returns True and decrements streak_freeze when a charge was consumed.
    Returns False when no charges remain.
    Caller is responsible for commit.
    """
    row = conn.execute(
        "SELECT streak_freeze FROM streak_state WHERE player_id='default'"
    ).fetchone()
    if row is None or int(row["streak_freeze"]) <= 0:
        return False
    conn.execute(
        "UPDATE streak_state SET streak_freeze = streak_freeze - 1 WHERE player_id='default'"
    )
    return True


def update_streak(conn: sqlite3.Connection, today: date) -> None:
    """Update streak_state for the default player based on `today`.

    Safe to call multiple times on the same date (idempotent after the first call).
    When a gap is detected, a streak freeze charge is consumed instead of resetting.
    Caller is responsible for commit.
    """
    conn.execute(
        "INSERT OR IGNORE INTO streak_state (player_id) VALUES ('default')"
    )
    row = conn.execute(
        "SELECT current_streak, longest_streak, last_active_date FROM streak_state WHERE player_id='default'"
    ).fetchone()

    last_str: str | None = row["last_active_date"]
    current: int = row["current_streak"]
    longest: int = row["longest_streak"]
    today_str = today.isoformat()

    if last_str == today_str:
        return  # already recorded for today — nothing to do

    if last_str is not None and date.fromisoformat(last_str) == _yesterday(today):
        current += 1
    else:
        # Gap detected: try to consume a freeze charge before resetting
        if last_str is not None and not consume_streak_freeze(conn):
            current = 1  # no freeze available — streak resets
        # if last_str is None it's first ever — streak starts at 1 below
        elif last_str is None:
            current = 1
        # else: freeze consumed → keep current unchanged

    longest = max(longest, current)
    conn.execute(
        "UPDATE streak_state SET current_streak=?, longest_streak=?, last_active_date=? WHERE player_id='default'",
        (current, longest, today_str),
    )


def get_streak(conn: sqlite3.Connection) -> dict:
    """Return current_streak, longest_streak, last_active_date for the default player."""
    conn.execute("INSERT OR IGNORE INTO streak_state (player_id) VALUES ('default')")
    row = conn.execute(
        "SELECT current_streak, longest_streak, last_active_date FROM streak_state WHERE player_id='default'"
    ).fetchone()
    return {
        "current_streak": row["current_streak"],
        "longest_streak": row["longest_streak"],
        "last_active_date": row["last_active_date"],
    }
