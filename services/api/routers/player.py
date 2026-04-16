import json
from fastapi import APIRouter, Request, HTTPException
from services.models.enums import Category
from services.progression.xp import get_total_xp, compute_level, compute_evolution_stage, compute_level_xp_range
from services.progression.streak import get_streak
from services.progression.config import EVOLUTION_STAGES
from services.progression.decay import get_dormancy_info

router = APIRouter()


@router.get("/profile")
def get_player_profile(request: Request) -> dict:
    db = request.app.state.db
    row = db.execute(
        "SELECT * FROM player_profile WHERE character_id='player_default'"
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Player not found")

    cat_rows = db.execute(
        "SELECT category, xp FROM player_category_xp WHERE character_id='player_default'"
    ).fetchall()
    # All categories always present — bars in the HUD appear even with 0 XP
    category_xp = {c.value: 0 for c in Category}
    category_xp.update({r["category"]: r["xp"] for r in cat_rows})
    total_xp = get_total_xp(db, "player_default")
    level = compute_level(total_xp)
    stage = compute_evolution_stage(level)
    level_xp_start, level_xp_end = compute_level_xp_range(level)
    streak = get_streak(db)
    dormancy = get_dormancy_info(db)

    try:
        visual = json.loads(row["visual"])
        equipped_items = json.loads(row["equipped_items"])
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="Corrupted player profile data") from exc

    # Compute next evolution stage level threshold (None when at max stage)
    next_stage_level: int | None = None
    if stage + 1 in EVOLUTION_STAGES:
        next_stage_level = EVOLUTION_STAGES[stage + 1][0]

    return {
        "character_id": row["character_id"],
        "name": row["name"],
        "total_xp": total_xp,
        "level": level,
        "level_xp_start": level_xp_start,
        "level_xp_end": level_xp_end,   # null when at max level
        "evolution_stage": stage,
        "next_evolution_level": next_stage_level,   # null when at max stage
        "streak_days": streak["current_streak"],
        "is_dormant": dormancy["is_dormant"],
        "dormant_days": dormancy["dormant_days"],
        "has_recovery_bonus": dormancy["has_recovery_bonus"],
        "category_xp": category_xp,
        "visual": visual,
        "equipped_items": equipped_items,
    }
