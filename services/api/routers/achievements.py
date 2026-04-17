from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()

_MAX_PINS = 3
_PLAYER_ID = "player_default"


def _pinned_ids(db) -> set[str]:
    rows = db.execute(
        "SELECT achievement_id FROM pinned_achievements WHERE player_id=?", (_PLAYER_ID,)
    ).fetchall()
    return {r["achievement_id"] for r in rows}


@router.get("")
def get_achievements(request: Request) -> list[dict]:
    """Return all achievement definitions with unlock and pin status."""
    db = request.app.state.db
    pinned = _pinned_ids(db)

    rows = db.execute(
        """
        SELECT a.achievement_id, a.name, a.description, a.condition_type, a.threshold,
               pa.unlocked_at
        FROM achievements a
        LEFT JOIN player_achievements pa
               ON pa.achievement_id = a.achievement_id
              AND pa.player_id = ?
        ORDER BY a.threshold ASC
        """,
        (_PLAYER_ID,),
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
            "pinned":         r["achievement_id"] in pinned,
        }
        for r in rows
    ]


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
