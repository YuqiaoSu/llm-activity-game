"""Daily goals — short-lived (24h) activity targets.

Goals are auto-generated from the suggestion engine once per UTC day.
Progress is updated alongside XP award in the sync agent.
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from services.progression.suggestions import get_suggestions


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def ensure_daily_goals(conn: sqlite3.Connection, player_id: str = "player_default") -> None:
    """Create today's goals if none exist yet (idempotent — safe to call every poll).

    Picks up to 3 'gap' or 'diversify' suggestions and converts them into
    concrete goals. Streak-danger and challenge-nudge suggestions are skipped
    (they aren't category-specific activity goals).
    """
    today = _today()
    existing = conn.execute(
        "SELECT COUNT(*) AS n FROM daily_goals WHERE player_id=? AND date=?",
        (player_id, today),
    ).fetchone()["n"]
    if existing > 0:
        return

    suggestions = get_suggestions(conn, player_id)
    now = datetime.now(timezone.utc).isoformat()
    added = 0
    for s in suggestions:
        if s["type"] not in ("gap", "diversify"):
            continue
        cat = s.get("category", "")
        if not cat:
            continue
        target_sec = s.get("target_min", 20) * 60
        conn.execute(
            """
            INSERT OR IGNORE INTO daily_goals
                (goal_id, player_id, date, category, target_sec, progress_sec, completed, created_at)
            VALUES (?, ?, ?, ?, ?, 0, 0, ?)
            """,
            (str(uuid.uuid4()), player_id, today, cat, target_sec, now),
        )
        added += 1
        if added >= 3:
            break
    conn.commit()


def update_daily_goal_progress(
    conn: sqlite3.Connection,
    category: str,
    duration_sec: int,
    player_id: str = "player_default",
) -> None:
    """Add `duration_sec` to today's goal progress for `category`.

    Marks the goal as completed when progress_sec >= target_sec.
    No-op if no goal exists for this category today.
    """
    today = _today()
    conn.execute(
        """
        UPDATE daily_goals
        SET progress_sec = MIN(progress_sec + ?, target_sec + 1),
            completed = CASE WHEN progress_sec + ? >= target_sec THEN 1 ELSE completed END
        WHERE player_id=? AND date=? AND category=?
        """,
        (duration_sec, duration_sec, player_id, today, category),
    )
    # No commit here — caller (agent) commits in batch


def get_daily_goals(
    conn: sqlite3.Connection,
    player_id: str = "player_default",
) -> list[dict]:
    """Return today's goal rows as dicts, ordered by completion then category."""
    today = _today()
    rows = conn.execute(
        """
        SELECT goal_id, category, target_sec, progress_sec, completed, created_at
        FROM daily_goals
        WHERE player_id=? AND date=?
        ORDER BY completed ASC, category ASC
        """,
        (player_id, today),
    ).fetchall()
    result = []
    for r in rows:
        target = r["target_sec"]
        progress = r["progress_sec"]
        result.append({
            "goal_id": r["goal_id"],
            "category": r["category"],
            "target_min": round(target / 60),
            "progress_min": round(progress / 60, 1),
            "progress_pct": min(100, int(progress / target * 100)) if target > 0 else 0,
            "completed": bool(r["completed"]),
        })
    return result
