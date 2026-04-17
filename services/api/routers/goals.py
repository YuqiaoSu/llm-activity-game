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
