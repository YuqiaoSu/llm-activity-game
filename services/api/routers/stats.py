from __future__ import annotations
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Request, Query
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


@router.get("/summary")
def get_stats_summary(request: Request) -> dict:
    """All-time career summary: XP, activity time, drops, categories."""
    db = request.app.state.db

    total_xp = get_total_xp(db, "player_default")
    level = compute_level(total_xp)

    # Per-category all-time XP
    cat_rows = db.execute(
        "SELECT category, xp FROM player_category_xp WHERE character_id='player_default'"
    ).fetchall()
    category_xp = {c.value: 0 for c in Category}
    category_xp.update({r["category"]: r["xp"] for r in cat_rows})

    # Total active minutes and total chunks from chunk_log
    agg = db.execute(
        "SELECT COUNT(*) AS chunks, COALESCE(SUM(duration_sec), 0) AS dur FROM chunk_log"
    ).fetchone()
    total_chunks: int = agg["chunks"]
    total_active_min: int = agg["dur"] // 60

    # Peak week XP (across all calendar weeks)
    peak_row = db.execute(
        """
        SELECT COALESCE(MAX(week_xp), 0) AS peak
        FROM (
            SELECT SUM(xp_awarded) AS week_xp
            FROM chunk_log
            GROUP BY strftime('%Y-%W', processed_at)
        )
        """
    ).fetchone()
    peak_week_xp: int = int(peak_row["peak"])

    # Distinct items ever collected
    items_collected: int = db.execute(
        "SELECT COUNT(DISTINCT item_id) FROM reward_ledger"
    ).fetchone()[0]

    return {
        "total_xp": total_xp,
        "level": level,
        "total_chunks": total_chunks,
        "total_active_min": total_active_min,
        "peak_week_xp": peak_week_xp,
        "items_collected": items_collected,
        "category_breakdown": category_xp,
    }


@router.get("/daily")
def get_daily_stats(
    request: Request,
    days: int = Query(default=7, ge=1, le=90),
) -> list[dict]:
    """Return per-day XP and duration aggregated from chunk_log.

    Each entry covers one UTC calendar date with total XP, total active
    minutes, and a per-category XP breakdown.  Returned newest-first,
    limited to the last `days` days (default 7, max 90).
    """
    db = request.app.state.db
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    rows = db.execute(
        """
        SELECT
            date(processed_at)   AS day,
            category,
            SUM(xp_awarded)      AS xp,
            SUM(duration_sec)    AS dur
        FROM chunk_log
        WHERE processed_at >= ?
        GROUP BY day, category
        ORDER BY day DESC, category
        """,
        (cutoff,),
    ).fetchall()

    # Fold (day, category) rows into one dict per day
    daily: dict[str, dict] = {}
    for row in rows:
        day = row["day"]
        if day not in daily:
            daily[day] = {
                "date": day,
                "total_xp": 0,
                "total_duration_sec": 0,
                "categories": {},
            }
        daily[day]["total_xp"] += row["xp"]
        daily[day]["total_duration_sec"] += row["dur"]
        daily[day]["categories"][row["category"]] = (
            daily[day]["categories"].get(row["category"], 0) + row["xp"]
        )

    return sorted(daily.values(), key=lambda d: d["date"], reverse=True)
