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

from datetime import date, datetime, timezone, timedelta
from fastapi import APIRouter, Request, Query

router = APIRouter()

_MAX_WEEKS = 52
_ALL_CATEGORIES = ["WORK", "GAME", "VIDEO", "SOCIAL", "EXPLORE", "SLEEP", "SPECIAL"]


def _month_offsets(n: int) -> list[str]:
    """Return list of 'YYYY-MM' strings for the last n calendar months, newest first."""
    today = date.today()
    months = []
    year, month = today.year, today.month
    for _ in range(n):
        months.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return months


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


@router.get("/seasonal")
def get_seasonal_leaderboard(
    request: Request,
    months: int = Query(default=6, ge=1, le=24),
) -> dict:
    """Return per-month XP totals for the last N calendar months, newest first.

    Each entry: {month, total_xp, active_min, by_category, is_current, is_best, rank}.
    Top-level: personal_best_xp, trend ("up"/"down"/"flat"), months.
    """
    db = request.app.state.db
    month_keys = _month_offsets(months)
    current_month = month_keys[0]

    # Aggregate XP per month × category in one query
    placeholders = ",".join("?" * len(month_keys))
    sql = (
        "SELECT strftime('%Y-%m', processed_at) AS month,"
        " category,"
        " COALESCE(SUM(xp_awarded), 0) AS xp,"
        " COALESCE(SUM(duration_sec), 0) AS duration_sec"
        " FROM chunk_log"
        " WHERE strftime('%Y-%m', processed_at) IN (" + placeholders + ")"
        " GROUP BY month, category"
    )
    rows = db.execute(sql, month_keys).fetchall()

    # Pivot rows into month → {category → xp, total_xp, total_sec}
    month_data: dict[str, dict] = {m: {"total_xp": 0, "total_sec": 0, "by_category": {}} for m in month_keys}
    for row in rows:
        m = row["month"]
        if m not in month_data:
            continue
        cat = row["category"]
        xp = int(row["xp"])
        month_data[m]["by_category"][cat] = xp
        month_data[m]["total_xp"] += xp
        month_data[m]["total_sec"] += int(row["duration_sec"])

    # Build entries list (newest first = month_keys order)
    entries: list[dict] = []
    for m in month_keys:
        d = month_data[m]
        by_cat = d["by_category"]
        for cat in _ALL_CATEGORIES:
            by_cat.setdefault(cat, 0)
        entries.append({
            "month": m,
            "total_xp": d["total_xp"],
            "active_min": round(d["total_sec"] / 60),
            "by_category": by_cat,
            "is_current": m == current_month,
            "is_best": False,
            "rank": 0,
        })

    # Compute personal best and ranks
    best_xp = max((e["total_xp"] for e in entries), default=0)
    sorted_xp = sorted({e["total_xp"] for e in entries}, reverse=True)
    xp_to_rank = {xp: i + 1 for i, xp in enumerate(sorted_xp)}

    for e in entries:
        e["is_best"] = e["total_xp"] == best_xp and best_xp > 0
        e["rank"] = xp_to_rank[e["total_xp"]]

    # Trend: current month vs previous month
    trend = "flat"
    if len(entries) >= 2:
        curr = entries[0]["total_xp"]
        prev = entries[1]["total_xp"]
        if curr > prev:
            trend = "up"
        elif curr < prev:
            trend = "down"

    return {
        "personal_best_xp": best_xp,
        "trend": trend,
        "months": entries,
    }
