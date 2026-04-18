import json
import sqlite3
from fastapi import APIRouter, Request, HTTPException
from services.models.enums import Category
from services.progression.xp import get_total_xp, compute_level, compute_evolution_stage, compute_level_xp_range
from services.progression.streak import get_streak
from services.progression.config import EVOLUTION_STAGES
from services.progression.decay import get_dormancy_info
from services.progression.mood import compute_mood

router = APIRouter()

# Static title catalog — earned state is computed at request time from live stats.
_TITLES: list[dict] = [
    {
        "title_id":   "newcomer",
        "label":      "Newcomer",
        "description": "Just getting started",
        "criteria":   "always",
    },
    {
        "title_id":   "focused_scholar",
        "label":      "Focused Scholar",
        "description": "Earn 500 XP in the WORK category",
        "criteria":   "work_xp_500",
    },
    {
        "title_id":   "explorer",
        "label":      "Explorer",
        "description": "Unlock 3 places",
        "criteria":   "places_unlocked_3",
    },
    {
        "title_id":   "streak_keeper",
        "label":      "Streak Keeper",
        "description": "Maintain a 7-day streak",
        "criteria":   "streak_7",
    },
    {
        "title_id":   "collector",
        "label":      "Collector",
        "description": "Own 10 different items",
        "criteria":   "items_10",
    },
    {
        "title_id":   "veteran",
        "label":      "Veteran",
        "description": "Reach level 10",
        "criteria":   "level_10",
    },
]

_TITLE_IDS: set[str] = {t["title_id"] for t in _TITLES}


def _check_earned(db: sqlite3.Connection, criteria: str) -> bool:
    """Return True when the player has satisfied the given criteria string."""
    match criteria:
        case "always":
            return True
        case "work_xp_500":
            row = db.execute(
                "SELECT COALESCE(xp, 0) AS xp FROM player_category_xp"
                " WHERE character_id='player_default' AND category='WORK'"
            ).fetchone()
            return bool(row and row["xp"] >= 500)
        case "places_unlocked_3":
            row = db.execute(
                "SELECT COUNT(*) AS n FROM places WHERE state='UNLOCKED'"
            ).fetchone()
            return bool(row and row["n"] >= 3)
        case "streak_7":
            streak = get_streak(db)
            return streak["current_streak"] >= 7
        case "items_10":
            row = db.execute(
                "SELECT COUNT(DISTINCT item_id) AS n FROM inventory"
                " WHERE character_id='player_default'"
            ).fetchone()
            return bool(row and row["n"] >= 10)
        case "level_10":
            return compute_level(get_total_xp(db, "player_default")) >= 10
        case _:
            return False


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
    mood = compute_mood(
        streak["current_streak"],
        dormancy["is_dormant"],
        dormancy["dormant_days"],
    )

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
        "mood": mood,
        "category_xp": category_xp,
        "visual": visual,
        "equipped_items": equipped_items,
        "equipped_title": row["equipped_title"] if "equipped_title" in row.keys() else None,
    }


@router.get("/titles")
def get_titles(request: Request) -> list[dict]:
    """Return all available titles with earned flag and equipped flag."""
    db = request.app.state.db
    row = db.execute(
        "SELECT equipped_title FROM player_profile WHERE character_id='player_default'"
    ).fetchone()
    equipped = row["equipped_title"] if row and "equipped_title" in row.keys() else None

    return [
        {
            "title_id":    t["title_id"],
            "label":       t["label"],
            "description": t["description"],
            "earned":      _check_earned(db, t["criteria"]),
            "equipped":    t["title_id"] == equipped,
        }
        for t in _TITLES
    ]


@router.post("/titles/{title_id}/equip")
def equip_title(title_id: str, request: Request) -> dict:
    """Equip a title. Returns 404 if title_id unknown, 409 if not yet earned."""
    if title_id not in _TITLE_IDS:
        raise HTTPException(status_code=404, detail="Title not found")
    db = request.app.state.db
    criteria = next(t["criteria"] for t in _TITLES if t["title_id"] == title_id)
    if not _check_earned(db, criteria):
        raise HTTPException(status_code=409, detail="Title not yet earned")
    db.execute(
        "UPDATE player_profile SET equipped_title=? WHERE character_id='player_default'",
        (title_id,),
    )
    db.commit()
    return {"equipped_title": title_id}
