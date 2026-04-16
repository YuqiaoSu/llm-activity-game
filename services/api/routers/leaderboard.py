"""Personal bests leaderboard — compares weekly XP across recent weeks.

GET /leaderboard/weekly?weeks=N   (default 8, max 52)

Returns a list of week summaries ordered newest-first, each entry containing:
  week_start        ISO date of Monday
  week_end          ISO date of Sunday
  total_xp          XP earned this week
  total_active_min  minutes of tracked activity
  is_current        True if this is the ongoing (partial) week
  is_best           True if this is the highest-XP week in the result set
  rank              1 = best week (position by XP, ties get same rank)

Top-level fields:
  personal_best_xp  the single highest weekly XP across all returned weeks
  trend             "up" / "down" / "flat" — current week vs previous week
  weeks             the list described above
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request, Query

router = APIRouter()

_MAX_WEEKS = 52


@router.get("/weekly")
def get_weekly_leaderboard(
    request: Request,
    weeks: int = Query(default=8, ge=1, le=_MAX_WEEKS),
) -> dict:
    db = request.app.state.db
    now = datetime.now(timezone.utc)

    # Anchor on this Monday
    days_since_monday = now.weekday()
    this_monday = (now - timedelta(days=days_since_monday)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    # Build week buckets newest-first
    entries: list[dict] = []
    for offset in range(weeks):
        monday = this_monday - timedelta(weeks=offset)
        sunday_end = monday + timedelta(days=7) - timedelta(seconds=1)

        week_start = monday.date().isoformat()
        week_end = (monday + timedelta(days=6)).date().isoformat()
        cutoff_start = monday.isoformat()
        cutoff_end = sunday_end.isoformat()

        row = db.execute(
            """
            SELECT COALESCE(SUM(xp_awarded), 0)   AS total_xp,
                   COALESCE(SUM(duration_sec), 0)  AS total_sec
            FROM chunk_log
            WHERE processed_at >= ? AND processed_at <= ?
            """,
            (cutoff_start, cutoff_end),
        ).fetchone()

        entries.append({
            "week_start": week_start,
            "week_end": week_end,
            "total_xp": int(row["total_xp"]),
            "total_active_min": round(int(row["total_sec"]) / 60),
            "is_current": offset == 0,
            "is_best": False,  # filled below
            "rank": 0,          # filled below
        })

    # Compute personal best and ranks
    best_xp = max((e["total_xp"] for e in entries), default=0)
    # Sort by xp descending for rank assignment (stable so weeks with same xp get same rank)
    sorted_xp = sorted({e["total_xp"] for e in entries}, reverse=True)
    xp_to_rank = {xp: i + 1 for i, xp in enumerate(sorted_xp)}

    for e in entries:
        e["is_best"] = e["total_xp"] == best_xp and best_xp > 0
        e["rank"] = xp_to_rank[e["total_xp"]]

    # Trend: compare current week vs previous week
    trend = "flat"
    if len(entries) >= 2:
        curr_xp = entries[0]["total_xp"]
        prev_xp = entries[1]["total_xp"]
        if curr_xp > prev_xp:
            trend = "up"
        elif curr_xp < prev_xp:
            trend = "down"

    return {
        "personal_best_xp": best_xp,
        "trend": trend,
        "weeks": entries,
    }
