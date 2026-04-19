"""Passive skill tree — GET /skills, POST /skills/{id}/unlock, POST /skills/{id}/upgrade."""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException

from services.progression.xp import get_total_xp, deduct_total_xp

router = APIRouter()


@router.get("")
def get_skills(request: Request) -> list[dict]:
    """Return all skills with unlocked, level, max_level, and can_unlock flags."""
    db = request.app.state.db
    total_xp = get_total_xp(db, "player_default")

    player_rows = db.execute(
        "SELECT skill_id, level FROM player_skills WHERE player_id='player_default'"
    ).fetchall()
    unlocked_levels: dict[str, int] = {r["skill_id"]: r["level"] for r in player_rows}

    rows = db.execute(
        "SELECT skill_id, name, description, xp_cost, effect_type, effect_params, max_level"
        " FROM skills ORDER BY xp_cost ASC"
    ).fetchall()

    result = []
    for row in rows:
        sid = row["skill_id"]
        unlocked = sid in unlocked_levels
        level = unlocked_levels.get(sid, 0)
        max_level = row["max_level"]
        # Upgrade cost = base_cost × 2^current_level (when unlocked and below max)
        upgrade_cost = row["xp_cost"] * (2 ** level) if unlocked and level < max_level else None
        can_upgrade = unlocked and level < max_level and upgrade_cost is not None and total_xp >= upgrade_cost
        result.append({
            "skill_id":     sid,
            "name":         row["name"],
            "description":  row["description"],
            "xp_cost":      row["xp_cost"],
            "effect_type":  row["effect_type"],
            "effect_params": json.loads(row["effect_params"]),
            "max_level":    max_level,
            "unlocked":     unlocked,
            "level":        level,
            "upgrade_cost": upgrade_cost,
            "can_upgrade":  can_upgrade,
            "can_unlock":   not unlocked and total_xp >= row["xp_cost"],
        })
    return result


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
        "INSERT INTO player_skills (player_id, skill_id, unlocked_at, level)"
        " VALUES ('player_default', ?, ?, 1)",
        (skill_id, datetime.now(timezone.utc).isoformat()),
    )
    db.commit()

    return {"skill_id": skill_id, "name": row["name"], "xp_spent": row["xp_cost"]}


@router.post("/{skill_id}/upgrade")
def upgrade_skill(skill_id: str, request: Request) -> dict:
    """Upgrade a skill to the next tier, spending XP = base_cost × 2^current_level.

    Returns 404 if skill not found.
    Returns 409 if not yet unlocked, or already at max level.
    Returns 402 if insufficient XP.
    """
    db = request.app.state.db

    skill_row = db.execute(
        "SELECT skill_id, name, xp_cost, max_level FROM skills WHERE skill_id=?",
        (skill_id,),
    ).fetchone()
    if not skill_row:
        raise HTTPException(status_code=404, detail="Skill not found")

    ps_row = db.execute(
        "SELECT level FROM player_skills WHERE player_id='player_default' AND skill_id=?",
        (skill_id,),
    ).fetchone()
    if not ps_row:
        raise HTTPException(status_code=409, detail="Skill not yet unlocked")

    current_level: int = int(ps_row["level"])
    max_level: int = int(skill_row["max_level"])
    if current_level >= max_level:
        raise HTTPException(status_code=409, detail="Skill already at max level")

    upgrade_cost: int = int(skill_row["xp_cost"]) * (2 ** current_level)
    total_xp = get_total_xp(db, "player_default")
    if total_xp < upgrade_cost:
        raise HTTPException(
            status_code=402,
            detail=f"Insufficient XP: have {total_xp}, need {upgrade_cost}",
        )

    deduct_total_xp(db, "player_default", upgrade_cost)
    new_level = current_level + 1
    db.execute(
        "UPDATE player_skills SET level=? WHERE player_id='player_default' AND skill_id=?",
        (new_level, skill_id),
    )
    db.commit()

    return {
        "skill_id":    skill_id,
        "name":        skill_row["name"],
        "new_level":   new_level,
        "max_level":   max_level,
        "xp_spent":    upgrade_cost,
    }
