import json
from fastapi import APIRouter, Request, HTTPException
from services.progression.xp import get_total_xp, compute_level, compute_evolution_stage

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
    category_xp = {r["category"]: r["xp"] for r in cat_rows}
    total_xp = get_total_xp(db, "player_default")
    level = compute_level(total_xp)
    stage = compute_evolution_stage(level)

    return {
        "character_id": row["character_id"],
        "name": row["name"],
        "total_xp": total_xp,
        "level": level,
        "evolution_stage": stage,
        "category_xp": category_xp,
        "visual": json.loads(row["visual"]),
        "equipped_items": json.loads(row["equipped_items"]),
    }
