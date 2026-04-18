"""Passive skill tree — GET /skills and POST /skills/{id}/unlock."""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException

from services.progression.xp import get_total_xp, deduct_total_xp

router = APIRouter()


@router.get("")
def get_skills(request: Request) -> list[dict]:
    """Return all skills with unlocked and can_unlock flags."""
    db = request.app.state.db
    total_xp = get_total_xp(db, "player_default")

    unlocked_ids: set[str] = {
        row["skill_id"]
        for row in db.execute(
            "SELECT skill_id FROM player_skills WHERE player_id='player_default'"
        ).fetchall()
    }

    rows = db.execute(
        "SELECT skill_id, name, description, xp_cost, effect_type, effect_params FROM skills"
        " ORDER BY xp_cost ASC"
    ).fetchall()

    return [
        {
            "skill_id":     row["skill_id"],
            "name":         row["name"],
            "description":  row["description"],
            "xp_cost":      row["xp_cost"],
            "effect_type":  row["effect_type"],
            "effect_params": json.loads(row["effect_params"]),
            "unlocked":     row["skill_id"] in unlocked_ids,
            "can_unlock":   row["skill_id"] not in unlocked_ids and total_xp >= row["xp_cost"],
        }
        for row in rows
    ]


@router.post("/{skill_id}/unlock")
def unlock_skill(skill_id: str, request: Request) -> dict:
    """Unlock a skill by spending XP.

    Returns 404 if skill not found.
    Returns 409 if already unlocked.
    Returns 402 if insufficient XP.
    """
    db = request.app.state.db

    row = db.execute(
        "SELECT skill_id, name, xp_cost FROM skills WHERE skill_id=?",
        (skill_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Skill not found")

    already = db.execute(
        "SELECT 1 FROM player_skills WHERE player_id='player_default' AND skill_id=?",
        (skill_id,),
    ).fetchone()
    if already:
        raise HTTPException(status_code=409, detail="Skill already unlocked")

    total_xp = get_total_xp(db, "player_default")
    if total_xp < row["xp_cost"]:
        raise HTTPException(
            status_code=402,
            detail=f"Insufficient XP: have {total_xp}, need {row['xp_cost']}",
        )

    deduct_total_xp(db, "player_default", row["xp_cost"])
    db.execute(
        "INSERT INTO player_skills (player_id, skill_id, unlocked_at) VALUES ('player_default', ?, ?)",
        (skill_id, datetime.now(timezone.utc).isoformat()),
    )
    db.commit()

    return {"skill_id": skill_id, "name": row["name"], "xp_spent": row["xp_cost"]}
