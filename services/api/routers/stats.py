from fastapi import APIRouter, Request
from services.models.enums import Category
from services.progression.xp import get_total_xp, compute_level, compute_evolution_stage
from services.progression.streak import get_streak

router = APIRouter()


@router.get("")
def get_stats(request: Request) -> dict:
    db = request.app.state.db

    total_xp = get_total_xp(db, "player_default")
    level = compute_level(total_xp)
    stage = compute_evolution_stage(level)

    cat_rows = db.execute(
        "SELECT category, xp FROM player_category_xp WHERE character_id='player_default'"
    ).fetchall()
    category_xp = {c.value: 0 for c in Category}
    category_xp.update({r["category"]: r["xp"] for r in cat_rows})

    top_category: str | None = max(
        (k for k, v in category_xp.items() if v > 0),
        key=lambda k: category_xp[k],
        default=None,
    )

    chunks_processed: int = db.execute(
        "SELECT COUNT(DISTINCT chunk_id) FROM reward_ledger"
    ).fetchone()[0]

    drops_total: int = db.execute(
        "SELECT COUNT(*) FROM reward_ledger"
    ).fetchone()[0]

    places_unlocked: int = db.execute(
        "SELECT COUNT(*) FROM places WHERE state='UNLOCKED'"
    ).fetchone()[0]

    streak = get_streak(db)

    return {
        "total_xp": total_xp,
        "level": level,
        "evolution_stage": stage,
        "category_xp": category_xp,
        "top_category": top_category,
        "chunks_processed": chunks_processed,
        "drops_total": drops_total,
        "places_unlocked": places_unlocked,
        "current_streak": streak["current_streak"],
        "longest_streak": streak["longest_streak"],
    }
