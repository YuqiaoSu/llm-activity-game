from fastapi import APIRouter, Request
from services.progression.daily_goals import (
    get_daily_goals,
    check_goal_streak_reward,
    get_goal_streak_status,
)

router = APIRouter()

_MILESTONES = [7, 14, 30]


@router.get("/daily")
def get_daily(request: Request) -> list[dict]:
    """Return today's daily goals for the player."""
    db = request.app.state.db
    return get_daily_goals(db)


@router.get("/streak")
def get_streak(request: Request) -> dict:
    """Return the player's current goal streak and next milestone info."""
    db = request.app.state.db
    return get_goal_streak_status(db)


@router.get("/stats")
def get_goal_stats(request: Request) -> dict:
    """Return all-time goal completion statistics for the player."""
    db = request.app.state.db

    rows = db.execute(
        """
        SELECT category,
               COUNT(*) AS total_set,
               SUM(completed) AS total_completed
        FROM daily_goals
        WHERE player_id = 'player_default'
        GROUP BY category
        """,
    ).fetchall()

    total_set = 0
    total_completed = 0
    by_category: list[dict] = []
    for row in rows:
        cat_set: int       = row["total_set"]
        cat_done: int      = row["total_completed"] or 0
        rate_pct: float    = round(cat_done / cat_set * 100, 1) if cat_set > 0 else 0.0
        total_set      += cat_set
        total_completed += cat_done
        by_category.append({
            "category":    row["category"],
            "set":         cat_set,
            "completed":   cat_done,
            "rate_pct":    rate_pct,
        })

    by_category.sort(key=lambda d: (-d["completed"], d["category"]))
    overall_rate = round(total_completed / total_set * 100, 1) if total_set > 0 else 0.0

    streak_row = db.execute(
        "SELECT current_streak, longest_streak FROM streak_state WHERE player_id='default'",
    ).fetchone()
    current_streak = streak_row["current_streak"] if streak_row else 0
    best_streak    = streak_row["longest_streak"] if streak_row else 0

    return {
        "total_goals_set":     total_set,
        "total_completed":     total_completed,
        "completion_rate_pct": overall_rate,
        "by_category":         by_category,
        "current_streak":      current_streak,
        "best_streak":         best_streak,
    }


@router.post("/claim-streak-reward")
def claim_streak_reward(request: Request) -> dict:
    """Trigger a goal-streak milestone check and award an item if one is due.

    Safe to call any time — idempotent within a calendar day.
    Returns the current streak state and whether a reward was granted.
    """
    db = request.app.state.db
    reward_granted = check_goal_streak_reward(db)
    status = get_goal_streak_status(db)
    return {
        "reward_granted": reward_granted,
        **status,
    }
