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


_FREEZE_BASE_COST = 100   # XP cost for first freeze; doubles per owned charge
_FREEZE_MAX = 3


@router.get("/streak-freeze")
def get_streak_freeze(request: Request) -> dict:
    """Return current streak freeze count and cost to buy the next charge."""
    db = request.app.state.db
    row = db.execute(
        "SELECT streak_freeze FROM streak_state WHERE player_id='default'"
    ).fetchone()
    count: int = int(row["streak_freeze"]) if row else 0
    cost = _FREEZE_BASE_COST * (2 ** count)
    return {
        "freeze_count": count,
        "max_freezes":  _FREEZE_MAX,
        "cost_next":    cost,
        "can_buy":      count < _FREEZE_MAX,
    }


@router.post("/streak-freeze/buy")
def buy_streak_freeze(request: Request) -> dict:
    """Spend XP to buy one streak freeze charge (max 3, cost doubles per owned).

    Returns 402 if insufficient XP.
    Returns 409 if already at max charges.
    """
    from services.progression.xp import get_total_xp, deduct_total_xp
    db = request.app.state.db

    row = db.execute(
        "SELECT streak_freeze FROM streak_state WHERE player_id='default'"
    ).fetchone()
    count: int = int(row["streak_freeze"]) if row else 0

    if count >= _FREEZE_MAX:
        raise HTTPException(status_code=409, detail="Already at maximum streak freeze charges")

    cost = _FREEZE_BASE_COST * (2 ** count)
    total_xp = get_total_xp(db, "player_default")
    if total_xp < cost:
        raise HTTPException(status_code=402, detail=f"Insufficient XP: need {cost}, have {total_xp}")

    deduct_total_xp(db, "player_default", cost)
    db.execute(
        "UPDATE streak_state SET streak_freeze = streak_freeze + 1 WHERE player_id='default'"
    )
    db.commit()

    new_count = count + 1
    new_cost = _FREEZE_BASE_COST * (2 ** new_count)
    return {
        "freeze_count": new_count,
        "max_freezes":  _FREEZE_MAX,
        "cost_next":    new_cost if new_count < _FREEZE_MAX else None,
        "xp_spent":     cost,
    }


_TIPS: list[str] = [
    "Log at least 10 minutes of activity daily to keep XP decay at bay!",
    "Donating items to places grants permanent +10% XP boosts — pick your best items.",
    "A 14-day streak unlocks the 'Streak Warrior' milestone achievement.",
    "Streak freezes protect your streak for one missed day — buy them when you're ahead.",
    "Your companion's mood affects how much XP your places earn. Stay active!",
    "Combo bonus: earn XP in 3+ different categories in one poll for a 10% boost.",
    "Higher luck increases your chance of RARE and EPIC drops — upgrade it when you can.",
    "Challenge progress notifications fire at 50% — use them to time your final push.",
    "The daily challenge awards 2× XP. Check which challenge is today's highlight.",
    "Focus streak tracks consecutive WORK/LEARN days. Build it for special rewards.",
    "Sell COMMON items you have in abundance to fund skill upgrades.",
    "Items placed in thematic slots grant extra XP bonuses to that place.",
    "Repair worn items before placing them — durability affects how long they last.",
    "XP milestones at 500, 1000, 2500, 5000, and 10000 XP each drop a bonus item.",
    "Pinned achievements show on your profile card — pick your proudest three.",
    "Achievement chains unlock in order — complete the parent to reveal the child.",
    "Invest XP in places to level them up fast — up to 500 XP per place per day.",
    "Wishlist rare items in the Catalogue so they glow when they drop.",
    "Weekly challenges reset Monday — check them early to plan your week.",
    "Export your profile anytime to back up your progress as a JSON snapshot.",
]


@router.get("/daily-tip")
def get_daily_tip(request: Request) -> dict:
    """Return the daily motivational tip, deterministically selected by today's date.

    The same tip is returned for all requests within the same UTC calendar day.
    """
    import hashlib

    today_key = date.today().isoformat().encode()
    tip_index: int = int(hashlib.md5(today_key).hexdigest(), 16) % len(_TIPS)
    return {"tip": _TIPS[tip_index], "tip_index": tip_index}


@router.get("/export")
def export_player_data(request: Request) -> dict:
    """Return the player's complete game state as a single JSON snapshot.

    Covers: profile, inventory, achievements, places, skills, last 7 days of XP,
    and the export timestamp. Read-only; no state is modified.
    """
    from datetime import datetime, timezone, timedelta
    db = request.app.state.db

    profile = get_player_profile(request)

    inv_rows = db.execute(
        """
        SELECT i.instance_id, i.item_id, i.acquired_at, i.expires_at, i.note,
               i.favorite, i.tags, i.placed_in,
               json_extract(d.data, '$.name')   AS item_name,
               json_extract(d.data, '$.rarity') AS rarity,
               json_extract(d.data, '$.category') AS category
        FROM inventory i
        LEFT JOIN item_definitions d ON i.item_id = d.item_id
        WHERE i.character_id='player_default'
        ORDER BY i.acquired_at DESC
        """
    ).fetchall()
    inventory = [dict(r) for r in inv_rows]

    ach_rows = db.execute(
        """
        SELECT a.achievement_id, a.name, a.description, a.condition_type, a.threshold,
               pa.unlocked_at
        FROM achievements a
        LEFT JOIN player_achievements pa
          ON pa.achievement_id = a.achievement_id AND pa.player_id = 'player_default'
        ORDER BY pa.unlocked_at IS NULL ASC, pa.unlocked_at ASC
        """
    ).fetchall()
    achievements = [
        {**dict(r), "unlocked": r["unlocked_at"] is not None}
        for r in ach_rows
    ]

    place_rows = db.execute(
        "SELECT place_id, name, place_type, state, xp, level FROM places ORDER BY name ASC"
    ).fetchall()
    places = [dict(r) for r in place_rows]

    skill_rows = db.execute(
        """
        SELECT s.skill_id, s.name, s.description, s.xp_cost,
               ps.level AS player_level
        FROM skills s
        LEFT JOIN player_skills ps ON ps.skill_id = s.skill_id AND ps.player_id = 'player_default'
        ORDER BY s.name ASC
        """
    ).fetchall()
    skills = [dict(r) for r in skill_rows]

    since = (datetime.now(timezone.utc) - timedelta(days=7)).date().isoformat()
    xp_rows = db.execute(
        """
        SELECT date(processed_at) AS day, SUM(xp_awarded) AS xp
        FROM chunk_log
        WHERE date(processed_at) > ?
        GROUP BY day
        ORDER BY day ASC
        """,
        (since,),
    ).fetchall()
    weekly_xp_7d = [{"day": r["day"], "xp": int(r["xp"])} for r in xp_rows]

    return {
        "profile":      profile,
        "inventory":    inventory,
        "achievements": achievements,
        "places":       places,
        "skills":       skills,
        "weekly_xp_7d": weekly_xp_7d,
        "export_at":    datetime.now(timezone.utc).isoformat(),
    }


_TIPS: list[str] = [
    "Your XP decay pauses if you log 10+ minutes of activity daily!",
    "Fuse 3 items of the same rarity to get one of the next tier.",
    "Donating items to a Level 5+ place grants a permanent 10% XP boost there.",
    "The Combo Bonus fires when you log ≥ 3 different categories in one session.",
    "Streak freezes cost 100 XP each and prevent one missed-day reset.",
    "Higher luck increases your chance of getting RARE and EPIC drops.",
    "Invest XP into a place to level it up and unlock better drop modifiers.",
    "Achievements come in chains — unlock the first to reveal the next.",
    "Timed challenge events add a multiplier to matching-category XP.",
    "Equip a title on your Profile Card to show off your achievements.",
    "The activity heatmap shows your 12-week intensity at a glance.",
    "Place upgrade previews let you see level-up impact before investing.",
    "Daily goals scale in difficulty as your goal streak grows.",
    "Sell unwanted items for XP — LEGENDARY items net 100 XP each.",
    "The recipe browser shows every craft path from COMMON to LEGENDARY.",
    "Passive skills can unlock extra roll chances on every poll.",
    "A Focus Streak builds when you log WORK or LEARN chunks every day.",
    "Wishlisted items get a ★ highlight when they drop in a poll.",
    "Check the challenge leaderboard to see where you rank against rivals.",
    "The activity calendar gives a colour-coded view of your productivity.",
]


@router.get("/daily-tip")
def get_daily_tip() -> dict:
    """Return today's motivational tip — deterministic for the full UTC day."""
    import hashlib
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).date().isoformat()
    idx = int(hashlib.md5(today.encode()).hexdigest(), 16) % len(_TIPS)
    return {"tip": _TIPS[idx], "tip_index": idx}


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
