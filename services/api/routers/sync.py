import httpx
from fastapi import APIRouter, Request, HTTPException
from datetime import datetime, timezone
from services.progression.streak import get_streak
from services.progression.decay import get_dormancy_info, RECOVERY_MULTIPLIER
from services.place_service.effects import load_active_effects, compute_set_bonuses, load_place_perks

router = APIRouter()

_STREAK_BONUS_THRESHOLD = 3
_STREAK_BONUS_FACTOR = 1.1


@router.get("/status")
def get_sync_status(request: Request) -> dict:
    db = request.app.state.db
    row = db.execute("SELECT * FROM sync_state WHERE player_id='default'").fetchone()
    if row:
        return {"last_cursor": row["last_cursor"], "last_sync_at": row["last_sync_at"]}
    return {"last_cursor": None, "last_sync_at": None}


@router.get("/multipliers")
def get_multipliers(request: Request) -> list[dict]:
    """Return all currently-active XP multipliers with their sources.

    Each entry: {source, multiplier, description, category}
    category is None for global multipliers.
    """
    db = request.app.state.db
    result: list[dict] = []

    # Streak bonus
    streak = get_streak(db)
    if streak["current_streak"] >= _STREAK_BONUS_THRESHOLD:
        result.append({
            "source": "streak",
            "multiplier": _STREAK_BONUS_FACTOR,
            "description": "Streak bonus (day %d)" % streak["current_streak"],
            "category": None,
        })

    # Dormancy recovery bonus
    dormancy = get_dormancy_info(db)
    if dormancy["has_recovery_bonus"]:
        result.append({
            "source": "recovery",
            "multiplier": RECOVERY_MULTIPLIER,
            "description": "Welcome back bonus",
            "category": None,
        })

    # Active challenge events
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    event_rows = db.execute(
        "SELECT label, category, multiplier FROM challenge_events "
        "WHERE starts_at <= ? AND ends_at >= ?",
        (now, now),
    ).fetchall()
    for row in event_rows:
        cat = row["category"]
        result.append({
            "source": "event",
            "multiplier": float(row["multiplier"]),
            "description": row["label"],
            "category": None if cat == "ALL" else cat,
        })

    # Place XP effects (xp_multiplier, set_bonus, category_xp_bonus)
    effects = load_active_effects(db) + compute_set_bonuses(db) + load_place_perks(db)
    for eff in effects:
        if eff.effect_type in ("xp_multiplier", "set_bonus"):
            result.append({
                "source": eff.effect_type,
                "multiplier": float(eff.params.get("factor", 1.0)),
                "description": eff.params.get("description", eff.effect_type.replace("_", " ").title()),
                "category": None,
            })
        elif eff.effect_type == "category_xp_bonus":
            cat = eff.params.get("category", "")
            result.append({
                "source": "category_bonus",
                "multiplier": float(eff.params.get("factor", 1.0)),
                "description": "%s XP boost" % cat.capitalize(),
                "category": cat or None,
            })

    return result


@router.post("/poll-now")
def poll_now(request: Request) -> dict:
    from services.sync_agent.rate_limiter import adaptive_cooldown
    db = request.app.state.db
    cooldown = adaptive_cooldown(db)
    # Apply adaptive cooldown to the live rate limiter
    request.app.state.sync_agent.rate_limiter.cooldown_sec = cooldown
    try:
        summary = request.app.state.sync_agent.poll_with_summary(manual=True)
    except httpx.HTTPError:
        return {"result": "ERROR", "cooldown_sec": cooldown,
                "total_xp": 0, "xp_by_category": {}, "chunks_processed": 0, "drops_earned": 0}
    summary["cooldown_sec"] = cooldown
    return summary
