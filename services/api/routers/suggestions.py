from fastapi import APIRouter, Request
from services.progression.suggestions import get_suggestions

router = APIRouter()


@router.get("")
def get_quest_suggestions(request: Request) -> list[dict]:
    """Return personalised short-term activity suggestions.

    Rules applied (in priority order):
    1. streak_danger — current streak > 0 and no activity yet today
    2. gap           — categories with zero activity in the last 7 days
    3. challenge_nudge — closest incomplete weekly challenge
    4. diversify     — single category > 70% of recent activity time
    """
    db = request.app.state.db
    return get_suggestions(db)
