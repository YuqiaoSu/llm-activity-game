import json
import math
import sqlite3
from datetime import date, timedelta
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, field_validator
from services.models.enums import Category
from services.progression.xp import get_total_xp, compute_level, compute_evolution_stage, compute_level_xp_range
from services.progression.streak import get_streak
from services.progression.config import EVOLUTION_STAGES
from services.progression.decay import get_dormancy_info
from services.progression.mood import compute_mood
from services.progression.focus_streak import get_focus_streak

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


class _SettingsBody(BaseModel):
    daily_xp_target: int

    @field_validator("daily_xp_target")
    @classmethod
    def validate_target(cls, v: int) -> int:
        if v < 1 or v > 10000:
            raise ValueError("daily_xp_target must be between 1 and 10000")
        return v


@router.get("/settings")
def get_player_settings(request: Request) -> dict:
    """Return the player's personal settings (daily XP target etc.)."""
    db = request.app.state.db
    row = db.execute(
        "SELECT daily_xp_target FROM player_settings WHERE player_id='player_default'"
    ).fetchone()
    return {"daily_xp_target": row["daily_xp_target"] if row else 100}


@router.patch("/settings")
def patch_player_settings(body: _SettingsBody, request: Request) -> dict:
    """Update the player's personal settings."""
    db = request.app.state.db
    db.execute(
        "INSERT OR REPLACE INTO player_settings (player_id, daily_xp_target) VALUES ('player_default', ?)",
        (body.daily_xp_target,),
    )
    db.commit()
    return {"daily_xp_target": body.daily_xp_target}


_LUCK_BASE_COST = 50   # XP cost to upgrade luck from level 5→6
_LUCK_MAX = 20


@router.get("/luck")
def get_player_luck(request: Request) -> dict:
    """Return the player's current luck stat and upgrade info."""
    from services.progression.xp import get_total_xp
    db = request.app.state.db
    row = db.execute(
        "SELECT luck FROM player_profile WHERE character_id='player_default'"
    ).fetchone()
    luck: int = row["luck"] if row else 5
    upgrade_cost = _LUCK_BASE_COST * (2 ** (luck - 5))
    total_xp = get_total_xp(db, "player_default")
    return {
        "luck":         luck,
        "max_luck":     _LUCK_MAX,
        "upgrade_cost": upgrade_cost,
        "can_upgrade":  luck < _LUCK_MAX and total_xp >= upgrade_cost,
    }


@router.post("/luck/upgrade")
def upgrade_player_luck(request: Request) -> dict:
    """Spend XP to increase luck by 1 (max 20).

    Returns 409 if already at max. Returns 402 if insufficient XP.
    """
    from services.progression.xp import get_total_xp, deduct_total_xp
    db = request.app.state.db
    row = db.execute(
        "SELECT luck FROM player_profile WHERE character_id='player_default'"
    ).fetchone()
    luck: int = row["luck"] if row else 5

    if luck >= _LUCK_MAX:
        raise HTTPException(status_code=409, detail="Luck is already at maximum")

    upgrade_cost = _LUCK_BASE_COST * (2 ** (luck - 5))
    total_xp = get_total_xp(db, "player_default")
    if total_xp < upgrade_cost:
        raise HTTPException(
            status_code=402,
            detail=f"Insufficient XP: need {upgrade_cost}, have {total_xp}",
        )

    deduct_total_xp(db, "player_default", upgrade_cost)
    new_luck = luck + 1
    db.execute(
        "UPDATE player_profile SET luck=? WHERE character_id='player_default'",
        (new_luck,),
    )
    db.commit()
    new_cost = _LUCK_BASE_COST * (2 ** (new_luck - 5))
    return {
        "luck":         new_luck,
        "max_luck":     _LUCK_MAX,
        "upgrade_cost": new_cost,
        "xp_spent":     upgrade_cost,
    }


class _RenameBody(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) == 0:
            raise ValueError("name must not be empty")
        if len(v) > 24:
            raise ValueError("name must be 24 characters or fewer")
        return v


@router.patch("/profile")
def patch_player_profile(body: _RenameBody, request: Request) -> dict:
    """Rename the player's companion. Validates 1-24 chars (trimmed)."""
    db = request.app.state.db
    db.execute(
        "UPDATE player_profile SET name=? WHERE character_id='player_default'",
        (body.name,),
    )
    db.commit()
    # Return the full updated profile so the client can refresh state in one round-trip.
    return get_player_profile(request)


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


@router.get("/xp-projection")
def get_xp_projection(request: Request) -> dict:
    """Return level-up ETA based on avg daily XP over the last 7 days.

    Returns {at_max_level: true} when the player is at the level cap.
    Returns eta_days=null / eta_date=null when avg_daily_xp=0 (no recent activity).
    """
    db = request.app.state.db
    total_xp = get_total_xp(db, "player_default")
    level = compute_level(total_xp)
    _, level_xp_end = compute_level_xp_range(level)

    if level_xp_end is None:
        return {"at_max_level": True}

    xp_to_next = max(0, level_xp_end - total_xp)

    since = (date.today() - timedelta(days=7)).isoformat()
    row = db.execute(
        "SELECT COALESCE(SUM(xp_awarded), 0) AS total FROM chunk_log"
        " WHERE date(processed_at) > ?",
        (since,),
    ).fetchone()
    week_xp: int = int(row["total"]) if row else 0
    avg_daily_xp: float = week_xp / 7.0

    if avg_daily_xp <= 0:
        return {
            "at_max_level":   False,
            "xp_to_next_level": xp_to_next,
            "avg_daily_xp":   0.0,
            "eta_days":       None,
            "eta_date":       None,
        }

    eta_days: int = math.ceil(xp_to_next / avg_daily_xp)
    eta_date: str = (date.today() + timedelta(days=eta_days)).isoformat()

    return {
        "at_max_level":     False,
        "xp_to_next_level": xp_to_next,
        "avg_daily_xp":     round(avg_daily_xp, 1),
        "eta_days":         eta_days,
        "eta_date":         eta_date,
    }


@router.get("/focus-streak")
def get_focus_streak_status(request: Request) -> dict:
    """Return the player's current focus streak — consecutive days with WORK/LEARN activity."""
    db = request.app.state.db
    return get_focus_streak(db)


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
