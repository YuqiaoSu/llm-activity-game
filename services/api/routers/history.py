from datetime import date, timedelta

from fastapi import APIRouter, Query, Request

router = APIRouter()

# XP thresholds for intensity tiers 0-4 (matches GitHub contribution graph style)
_INTENSITY_THRESHOLDS = [0, 30, 80, 180]  # 0→none, 1→low, 2→med, 3→high, 4→very high


def _intensity(xp: int) -> int:
    if xp <= 0:
        return 0
    for i, threshold in enumerate(reversed(_INTENSITY_THRESHOLDS)):
        if xp > threshold:
            return len(_INTENSITY_THRESHOLDS) - i
    return 1

_LIMIT = 50
_ALL_CATEGORIES = ["WORK", "GAME", "VIDEO", "SOCIAL", "EXPLORE", "SLEEP", "SPECIAL"]


@router.get("/daily")
def get_daily_history(
    request: Request,
    days: int = Query(default=14, ge=1, le=90),
) -> list[dict]:
    """Return per-day XP and duration grouped by category for the last N days.

    Each entry: {date, total_xp, total_duration_sec, by_category: {CAT: xp, ...}}.
    Days are UTC dates, newest first.  Days with zero activity are omitted.
    """
    db = request.app.state.db
    rows = db.execute(
        """
        SELECT
            DATE(processed_at) AS day,
            category,
            SUM(xp_awarded)    AS xp,
            SUM(duration_sec)  AS duration_sec
        FROM chunk_log
        WHERE processed_at >= DATE('now', ? || ' days')
        GROUP BY day, category
        ORDER BY day DESC, category ASC
        """,
        (f"-{days}",),
    ).fetchall()

    # Pivot into per-day dict
    day_map: dict[str, dict] = {}
    for row in rows:
        day = row["day"]
        if day not in day_map:
            day_map[day] = {
                "date": day,
                "total_xp": 0,
                "total_duration_sec": 0,
                "by_category": {},
            }
        day_map[day]["total_xp"] += row["xp"]
        day_map[day]["total_duration_sec"] += row["duration_sec"]
        day_map[day]["by_category"][row["category"]] = row["xp"]

    # Return newest-first; fill missing categories with 0
    result = []
    for entry in sorted(day_map.values(), key=lambda e: e["date"], reverse=True):
        for cat in _ALL_CATEGORIES:
            entry["by_category"].setdefault(cat, 0)
        result.append(entry)
    return result


@router.get("/heatmap")
def get_heatmap(
    request: Request,
    weeks: int = Query(default=12, ge=1, le=52),
) -> list[dict]:
    """Return per-day XP totals and intensity tiers for the last N weeks.

    Returns exactly weeks×7 entries, oldest first (Sunday of the oldest week).
    Each entry: {date, total_xp, intensity (0-4)}.
    Days with no activity have total_xp=0, intensity=0.
    """
    db = request.app.state.db
    total_days = weeks * 7

    # Anchor to today; go back total_days days
    today = date.today()
    start = today - timedelta(days=total_days - 1)

    # Fetch daily XP aggregates from chunk_log
    rows = db.execute(
        """
        SELECT DATE(processed_at) AS day, SUM(xp_awarded) AS total_xp
        FROM chunk_log
        WHERE DATE(processed_at) >= ?
        GROUP BY day
        """,
        (start.isoformat(),),
    ).fetchall()

    xp_by_day: dict[str, int] = {r["day"]: int(r["total_xp"]) for r in rows}

    result: list[dict] = []
    for i in range(total_days):
        d = (start + timedelta(days=i)).isoformat()
        xp = xp_by_day.get(d, 0)
        result.append({"date": d, "total_xp": xp, "intensity": _intensity(xp)})
    return result


@router.get("")
def get_history(request: Request) -> list[dict]:
    db = request.app.state.db

    rows = db.execute(
        """
        SELECT log_id, chunk_id, category, xp_awarded, duration_sec, processed_at
        FROM chunk_log
        ORDER BY processed_at DESC
        LIMIT ?
        """,
        (_LIMIT,),
    ).fetchall()

    result: list[dict] = []
    for row in rows:
        drop_count: int = db.execute(
            "SELECT COUNT(*) FROM reward_ledger WHERE chunk_id = ?",
            (row["chunk_id"],),
        ).fetchone()[0]
        result.append({
            "chunk_id": row["chunk_id"],
            "category": row["category"],
            "xp_awarded": row["xp_awarded"],
            "duration_sec": row["duration_sec"],
            "processed_at": row["processed_at"],
            "drops": drop_count,
        })

    return result
