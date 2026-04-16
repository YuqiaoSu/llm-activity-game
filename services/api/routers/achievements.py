from fastapi import APIRouter, Request

router = APIRouter()


@router.get("")
def get_achievements(request: Request) -> list[dict]:
    """Return all achievement definitions with unlock status for the default player."""
    db = request.app.state.db

    rows = db.execute(
        """
        SELECT a.achievement_id, a.name, a.description, a.condition_type, a.threshold,
               pa.unlocked_at
        FROM achievements a
        LEFT JOIN player_achievements pa
               ON pa.achievement_id = a.achievement_id
              AND pa.player_id = 'player_default'
        ORDER BY a.threshold ASC
        """
    ).fetchall()

    return [
        {
            "achievement_id": r["achievement_id"],
            "name":           r["name"],
            "description":    r["description"],
            "condition_type": r["condition_type"],
            "threshold":      r["threshold"],
            "unlocked":       r["unlocked_at"] is not None,
            "unlocked_at":    r["unlocked_at"],
        }
        for r in rows
    ]
