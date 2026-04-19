from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Query
from services.progression.xp import get_total_xp, compute_level
from services.progression.streak import get_streak

router = APIRouter()

_MAX_PINS = 3
_PLAYER_ID = "player_default"


def _pinned_ids(db) -> set[str]:
    rows = db.execute(
        "SELECT achievement_id FROM pinned_achievements WHERE player_id=?", (_PLAYER_ID,)
    ).fetchall()
    return {r["achievement_id"] for r in rows}


def _player_progress_values(db) -> dict[str, int]:
    """Compute the current player stat for each condition_type in a single DB pass."""
    total_xp = get_total_xp(db, "player_default")
    level = compute_level(total_xp)
    streak = get_streak(db)
    items_row = db.execute(
        "SELECT COUNT(DISTINCT item_id) AS n FROM inventory WHERE character_id='player_default'"
    ).fetchone()
    return {
        "total_xp": total_xp,
        "level": level,
        "streak": streak["current_streak"],
        "items_collected": int(items_row["n"]) if items_row else 0,
    }


def _build_chain_depth(rows: list) -> dict[str, int]:
    """Compute chain_depth (0=root) for each achievement_id by walking parent links."""
    parent_map: dict[str, str | None] = {
        r["achievement_id"]: r["parent_achievement_id"] for r in rows
    }
    depth_cache: dict[str, int] = {}

    def _depth(aid: str) -> int:
        if aid in depth_cache:
            return depth_cache[aid]
        parent = parent_map.get(aid)
        if parent is None or parent not in parent_map:
            depth_cache[aid] = 0
        else:
            depth_cache[aid] = _depth(parent) + 1
        return depth_cache[aid]

    for aid in parent_map:
        _depth(aid)
    return depth_cache


@router.get("")
def get_achievements(
    request: Request,
    unlocked: bool | None = Query(default=None, description="Filter by unlocked state"),
    search: str | None = Query(default=None, description="Search by name (case-insensitive substring)"),
) -> list[dict]:
    """Return achievement definitions with optional unlocked/search filters."""
    db = request.app.state.db
    pinned = _pinned_ids(db)
    progress_vals = _player_progress_values(db)

    rows = db.execute(
        """
        SELECT a.achievement_id, a.name, a.description, a.condition_type, a.threshold,
               a.parent_achievement_id, pa.unlocked_at
        FROM achievements a
        LEFT JOIN player_achievements pa
               ON pa.achievement_id = a.achievement_id
              AND pa.player_id = ?
        ORDER BY a.threshold ASC
        """,
        (_PLAYER_ID,),
    ).fetchall()

    chain_depths = _build_chain_depth(rows)
    unlocked_ids: set[str] = {r["achievement_id"] for r in rows if r["unlocked_at"] is not None}

    # parent_map for chain_complete check: child → parent
    parent_map: dict[str, str | None] = {
        r["achievement_id"]: r["parent_achievement_id"] for r in rows
    }

    def _chain_complete(aid: str) -> bool:
        parent = parent_map.get(aid)
        while parent is not None:
            if parent not in unlocked_ids:
                return False
            parent = parent_map.get(parent)
        return True

    search_lower = search.strip().lower() if search else None
    result = []
    for r in rows:
        threshold = int(r["threshold"])
        ctype = r["condition_type"]
        is_unlocked = r["unlocked_at"] is not None
        aid = r["achievement_id"]

        # Apply unlocked filter
        if unlocked is not None and is_unlocked != unlocked:
            continue
        # Apply search filter
        if search_lower and search_lower not in r["name"].lower():
            continue

        if is_unlocked:
            progress = threshold
            progress_pct = 100
        else:
            current = progress_vals.get(ctype, 0)
            progress = min(current, threshold)
            progress_pct = min(100, round(progress / threshold * 100)) if threshold > 0 else 100
        result.append({
            "achievement_id":       aid,
            "name":                 r["name"],
            "description":          r["description"],
            "condition_type":       ctype,
            "threshold":            threshold,
            "unlocked":             is_unlocked,
            "unlocked_at":          r["unlocked_at"],
            "pinned":               aid in pinned,
            "progress":             progress,
            "progress_pct":         progress_pct,
            "parent_achievement_id": r["parent_achievement_id"],
            "chain_depth":          chain_depths.get(aid, 0),
            "chain_complete":       _chain_complete(aid),
        })
    return result


@router.get("/pinned")
def get_pinned(request: Request) -> list[dict]:
    """Return up to 3 pinned achievements in pin_order, with full unlock details."""
    db = request.app.state.db

    rows = db.execute(
        """
        SELECT a.achievement_id, a.name, a.description, a.condition_type, a.threshold,
               pa.unlocked_at, pin.pin_order, pin.pinned_at
        FROM pinned_achievements pin
        JOIN achievements a ON a.achievement_id = pin.achievement_id
        LEFT JOIN player_achievements pa
               ON pa.achievement_id = pin.achievement_id
              AND pa.player_id = ?
        WHERE pin.player_id = ?
        ORDER BY pin.pin_order ASC
        """,
        (_PLAYER_ID, _PLAYER_ID),
    ).fetchall()

    return [
        {
            "achievement_id": r["achievement_id"],
            "name":           r["name"],
            "description":    r["description"],
            "condition_type": r["condition_type"],
            "threshold":      r["threshold"],
            "unlocked":       r["unlocked_at"] is not None,
            "unlocked_at":    r["unlocked_at"],
            "pin_order":      r["pin_order"],
            "pinned_at":      r["pinned_at"],
        }
        for r in rows
    ]


@router.post("/{achievement_id}/pin")
def pin_achievement(achievement_id: str, request: Request) -> dict:
    """Pin an unlocked achievement to the showcase (max 3 slots).

    Returns 404 if the achievement doesn't exist or isn't unlocked.
    Returns 409 if already pinned.
    Returns 400 if all 3 slots are occupied.
    """
    db = request.app.state.db

    unlocked = db.execute(
        "SELECT 1 FROM player_achievements WHERE player_id=? AND achievement_id=?",
        (_PLAYER_ID, achievement_id),
    ).fetchone()
    if unlocked is None:
        raise HTTPException(status_code=404, detail="Achievement not unlocked or does not exist")

    existing = db.execute(
        "SELECT 1 FROM pinned_achievements WHERE player_id=? AND achievement_id=?",
        (_PLAYER_ID, achievement_id),
    ).fetchone()
    if existing:
        raise HTTPException(status_code=409, detail="Achievement is already pinned")

    count = db.execute(
        "SELECT COUNT(*) AS n FROM pinned_achievements WHERE player_id=?", (_PLAYER_ID,)
    ).fetchone()["n"]
    if count >= _MAX_PINS:
        raise HTTPException(status_code=400, detail=f"All {_MAX_PINS} pin slots are occupied")

    next_order = int(count) + 1
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO pinned_achievements (player_id, achievement_id, pin_order, pinned_at) "
        "VALUES (?, ?, ?, ?)",
        (_PLAYER_ID, achievement_id, next_order, now),
    )
    db.commit()
    return {"achievement_id": achievement_id, "pin_order": next_order, "pinned_at": now}


@router.delete("/{achievement_id}/pin")
def unpin_achievement(achievement_id: str, request: Request) -> dict:
    """Remove an achievement from the showcase.

    Returns 404 if the achievement is not currently pinned.
    After removal, remaining pins are re-ordered (1-based, gap-free).
    """
    db = request.app.state.db

    existing = db.execute(
        "SELECT pin_order FROM pinned_achievements WHERE player_id=? AND achievement_id=?",
        (_PLAYER_ID, achievement_id),
    ).fetchone()
    if existing is None:
        raise HTTPException(status_code=404, detail="Achievement is not pinned")

    removed_order = int(existing["pin_order"])
    db.execute(
        "DELETE FROM pinned_achievements WHERE player_id=? AND achievement_id=?",
        (_PLAYER_ID, achievement_id),
    )
    # Close the gap: decrement pin_order for all pins that were after the removed one
    db.execute(
        "UPDATE pinned_achievements SET pin_order = pin_order - 1 "
        "WHERE player_id=? AND pin_order > ?",
        (_PLAYER_ID, removed_order),
    )
    db.commit()
    return {"achievement_id": achievement_id, "unpinned": True}
