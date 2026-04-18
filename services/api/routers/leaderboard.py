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
from fastapi import APIRouter, Request, Query, HTTPException
from services.progression.xp import get_total_xp, compute_level
from services.progression.streak import get_streak

router = APIRouter()

_MAX_WEEKS = 52
_ALL_CATEGORIES = ["WORK", "GAME", "VIDEO", "SOCIAL", "EXPLORE", "SLEEP", "SPECIAL"]

# Seeded ghost players for the friend-comparison and category-race features.
# These are read-only fixtures — no DB rows needed.
# weekly_by_category sums must equal weekly_xp.
_GHOST_PLAYERS: dict[str, dict] = {
    "ghost_focus": {
        "player_id": "ghost_focus",
        "name": "FocusBot",
        "level": 8,
        "total_xp": 3200,
        "weekly_xp": 520,
        "streak_days": 7,
        "weekly_by_category": {
            "WORK": 380, "EXPLORE": 80, "GAME": 40, "VIDEO": 10,
            "SOCIAL": 5, "SLEEP": 5, "SPECIAL": 0,
        },
    },
    "ghost_casual": {
        "player_id": "ghost_casual",
        "name": "CasualMax",
        "level": 4,
        "total_xp": 850,
        "weekly_xp": 110,
        "streak_days": 2,
        "weekly_by_category": {
            "GAME": 60, "SOCIAL": 30, "VIDEO": 10, "WORK": 5,
            "EXPLORE": 5, "SLEEP": 0, "SPECIAL": 0,
        },
    },
    "ghost_grinder": {
        "player_id": "ghost_grinder",
        "name": "XP Grinder",
        "level": 15,
        "total_xp": 9800,
        "weekly_xp": 1200,
        "streak_days": 21,
        "weekly_by_category": {
            "WORK": 500, "GAME": 300, "VIDEO": 200,
            "SOCIAL": 100, "EXPLORE": 100, "SLEEP": 0, "SPECIAL": 0,
        },
    },
}


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


@router.get("/compare")
def get_compare(
    request: Request,
    other_id: str = Query(..., description="ID of the ghost player to compare against"),
) -> dict:
    """Return a side-by-side comparison of the player vs a ghost friend.

    Response fields:
      you        — dict with player_id, name, level, total_xp, weekly_xp, streak_days
      other      — same shape for the ghost player
      winner     — "you" | "other" | "tie"  (based on total_xp)
      available  — list of {player_id, name} ghost players (for discovery)
    """
    if other_id not in _GHOST_PLAYERS:
        raise HTTPException(
            status_code=404,
            detail=f"Ghost player '{other_id}' not found. Available: {list(_GHOST_PLAYERS)}",
        )

    db = request.app.state.db

    # Real player stats
    total_xp = get_total_xp(db, "player_default")
    level = compute_level(total_xp)
    streak = get_streak(db)

    # Weekly XP for the real player (Mon 00:00 UTC → now)
    now = datetime.now(timezone.utc)
    days_since_monday = now.weekday()
    this_monday = (now - timedelta(days=days_since_monday)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    row = db.execute(
        "SELECT COALESCE(SUM(xp_awarded), 0) AS wk FROM chunk_log WHERE processed_at >= ?",
        (this_monday.isoformat(),),
    ).fetchone()
    weekly_xp = int(row["wk"])

    profile_row = db.execute(
        "SELECT name FROM player_profile WHERE character_id='player_default'"
    ).fetchone()
    player_name = profile_row["name"] if profile_row else "You"

    you: dict = {
        "player_id": "player_default",
        "name": player_name,
        "level": level,
        "total_xp": total_xp,
        "weekly_xp": weekly_xp,
        "streak_days": streak["current_streak"],
    }

    other: dict = _GHOST_PLAYERS[other_id]

    if you["total_xp"] > other["total_xp"]:
        winner = "you"
    elif you["total_xp"] < other["total_xp"]:
        winner = "other"
    else:
        winner = "tie"

    return {
        "you": you,
        "other": other,
        "winner": winner,
        "available": [{"player_id": k, "name": v["name"]} for k, v in _GHOST_PLAYERS.items()],
    }


@router.get("/race")
def get_race(
    request: Request,
    other_id: str = Query(..., description="Ghost player ID to race against"),
) -> dict:
    """Return this week's per-category XP race between the player and a ghost.

    Response:
      other_name   — display name of the ghost
      categories   — list of {category, your_xp, their_xp, leader ("you"|"other"|"tie")}
      you_wins     — count of categories where you lead
      other_wins   — count of categories where the ghost leads
    """
    if other_id not in _GHOST_PLAYERS:
        raise HTTPException(
            status_code=404,
            detail=f"Ghost player '{other_id}' not found. Available: {list(_GHOST_PLAYERS)}",
        )

    db = request.app.state.db
    ghost = _GHOST_PLAYERS[other_id]
    ghost_by_cat: dict[str, int] = ghost.get("weekly_by_category", {})

    # Your weekly XP per category (since this Monday UTC)
    now = datetime.now(timezone.utc)
    days_since_monday = now.weekday()
    this_monday = (now - timedelta(days=days_since_monday)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    rows = db.execute(
        """
        SELECT category, COALESCE(SUM(xp_awarded), 0) AS xp
        FROM chunk_log
        WHERE processed_at >= ?
        GROUP BY category
        """,
        (this_monday.isoformat(),),
    ).fetchall()
    your_by_cat: dict[str, int] = {r["category"]: int(r["xp"]) for r in rows}

    categories: list[dict] = []
    you_wins = 0
    other_wins = 0
    for cat in _ALL_CATEGORIES:
        your_xp = your_by_cat.get(cat, 0)
        their_xp = ghost_by_cat.get(cat, 0)
        if your_xp > their_xp:
            leader = "you"
            you_wins += 1
        elif your_xp < their_xp:
            leader = "other"
            other_wins += 1
        else:
            leader = "tie"
        categories.append({
            "category": cat,
            "your_xp": your_xp,
            "their_xp": their_xp,
            "leader": leader,
        })

    return {
        "other_name": ghost["name"],
        "other_id": other_id,
        "categories": categories,
        "you_wins": you_wins,
        "other_wins": other_wins,
    }
