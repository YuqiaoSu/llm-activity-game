"""Weekly recap endpoint — aggregated summary of the player's week."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request, Query
from services.progression.xp import compute_level

router = APIRouter()


@router.get("/weekly")
def get_weekly_recap(
    request: Request,
    weeks_ago: int = Query(default=0, ge=0, le=11),
) -> dict:
    """Return an aggregated summary of one calendar week's activity.

    weeks_ago=0 means the current week (Mon–Sun UTC), 1 means last week, etc.
    The week boundary is Monday 00:00 UTC.

    Returns:
      week_start          ISO date of Monday
      week_end            ISO date of Sunday
      total_active_min    total minutes of tracked activity
      total_xp_earned     XP awarded this week
      category_breakdown  {category: {xp, active_min}} for each active category
      top_category        category with most XP this week (null if none)
      items_found         number of distinct item types dropped
      challenges_completed count of weekly challenges completed
      achievements_unlocked count of achievements unlocked
      level_start         level at week start (estimated from XP delta)
      level_end           current level (or end-of-week level)
      streak_at_end       current streak value (proxy for end-of-week)
    """
    db = request.app.state.db
    now = datetime.now(timezone.utc)
    # Find the Monday of the target week
    days_since_monday = now.weekday()
    this_monday = (now - timedelta(days=days_since_monday)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    target_monday = this_monday - timedelta(weeks=weeks_ago)
    target_sunday = target_monday + timedelta(days=6, hours=23, minutes=59, seconds=59)

    week_start = target_monday.date().isoformat()
    week_end = target_sunday.date().isoformat()
    cutoff_start = target_monday.isoformat()
    cutoff_end = target_sunday.isoformat()

    # ── activity from chunk_log ───────────────────────────────────────────────
    chunk_rows = db.execute(
        """
        SELECT category, SUM(xp_awarded) AS xp, SUM(duration_sec) AS dur_sec
        FROM chunk_log
        WHERE processed_at >= ? AND processed_at <= ?
        GROUP BY category
        """,
        (cutoff_start, cutoff_end),
    ).fetchall()

    category_breakdown: dict[str, dict] = {}
    total_xp = 0
    total_sec = 0
    for row in chunk_rows:
        xp = row["xp"] or 0
        dur = row["dur_sec"] or 0
        category_breakdown[row["category"]] = {
            "xp": xp,
            "active_min": round(dur / 60),
        }
        total_xp += xp
        total_sec += dur

    top_category: str | None = (
        max(category_breakdown, key=lambda c: category_breakdown[c]["xp"])
        if category_breakdown else None
    )

    # ── drops from reward_ledger ──────────────────────────────────────────────
    items_row = db.execute(
        """
        SELECT COUNT(DISTINCT item_id) AS n
        FROM reward_ledger
        WHERE awarded_at >= ? AND awarded_at <= ?
        """,
        (cutoff_start, cutoff_end),
    ).fetchone()
    items_found: int = items_row["n"] if items_row else 0

    # ── completed challenges ──────────────────────────────────────────────────
    challenges_row = db.execute(
        """
        SELECT COUNT(*) AS n
        FROM player_weekly_progress
        WHERE player_id='default'
          AND completed=1
          AND week_start >= ? AND week_start <= ?
        """,
        (week_start, week_end),
    ).fetchone()
    challenges_completed: int = challenges_row["n"] if challenges_row else 0

    # ── achievements unlocked ─────────────────────────────────────────────────
    ach_row = db.execute(
        """
        SELECT COUNT(*) AS n
        FROM player_achievements
        WHERE player_id='default'
          AND unlocked_at >= ? AND unlocked_at <= ?
        """,
        (cutoff_start, cutoff_end),
    ).fetchone()
    achievements_unlocked: int = ach_row["n"] if ach_row else 0

    # ── level at start/end (estimated) ────────────────────────────────────────
    # Compute XP earned before the week to estimate start level
    pre_week_xp = db.execute(
        """
        SELECT COALESCE(SUM(xp_awarded), 0) AS xp
        FROM chunk_log
        WHERE processed_at < ?
        """,
        (cutoff_start,),
    ).fetchone()["xp"]
    level_start = compute_level(pre_week_xp)
    level_end = compute_level(pre_week_xp + total_xp)

    # ── streak ────────────────────────────────────────────────────────────────
    streak_row = db.execute(
        "SELECT current_streak FROM streak_state WHERE player_id='default'"
    ).fetchone()
    streak_val: int = streak_row["current_streak"] if streak_row else 0

    return {
        "week_start": week_start,
        "week_end": week_end,
        "total_active_min": round(total_sec / 60),
        "total_xp_earned": total_xp,
        "category_breakdown": category_breakdown,
        "top_category": top_category,
        "items_found": items_found,
        "challenges_completed": challenges_completed,
        "achievements_unlocked": achievements_unlocked,
        "level_start": level_start,
        "level_end": level_end,
        "streak_at_end": streak_val,
    }
