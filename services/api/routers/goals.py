from fastapi import APIRouter, Request
from services.progression.daily_goals import get_daily_goals

router = APIRouter()


@router.get("/daily")
def get_daily(request: Request) -> list[dict]:
    """Return today's daily goals for the player.

    Goals are generated automatically on the first poll of each day.
    Each entry includes category, target_min, progress_min, progress_pct,
    and a completed flag.
    """
    db = request.app.state.db
    return get_daily_goals(db)
