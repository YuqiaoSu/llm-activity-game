from __future__ import annotations
from fastapi import APIRouter, Request
from services.progression.weekly_challenges import get_week_start
from datetime import datetime, timezone

router = APIRouter()


@router.get("")
def get_challenges(request: Request) -> list[dict]:
    """Return all weekly challenge definitions with current-week progress.

    Each entry includes the challenge definition fields plus the player's
    progress and completion status for the running ISO week.
    """
    db = request.app.state.db
    week_start = get_week_start(datetime.now(timezone.utc))

    rows = db.execute(
        """
        SELECT
            c.challenge_id,
            c.name,
            c.description,
            c.category,
            c.metric,
            c.threshold,
            COALESCE(p.progress, 0)   AS progress,
            COALESCE(p.completed, 0)  AS completed,
            COALESCE(p.week_start, ?) AS week_start
        FROM weekly_challenges c
        LEFT JOIN player_weekly_progress p
            ON p.challenge_id = c.challenge_id
            AND p.player_id   = 'player_default'
            AND p.week_start  = ?
        ORDER BY c.challenge_id
        """,
        (week_start, week_start),
    ).fetchall()

    return [
        {
            "challenge_id": row["challenge_id"],
            "name":         row["name"],
            "description":  row["description"],
            "category":     row["category"],
            "metric":       row["metric"],
            "threshold":    row["threshold"],
            "progress":     row["progress"],
            "completed":    bool(row["completed"]),
            "week_start":   row["week_start"],
        }
        for row in rows
    ]
