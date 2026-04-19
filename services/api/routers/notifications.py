from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel
from services.reward_ledger.ledger import get_pending_notifications

router = APIRouter()


@router.get("/count")
def get_notification_count(request: Request) -> dict:
    """Return the count of unread (unacknowledged) notifications."""
    db = request.app.state.db
    row = db.execute(
        "SELECT COUNT(*) AS n FROM pending_notifications"
        " WHERE character_id='player_default' AND acknowledged=0"
    ).fetchone()
    return {"unread": row["n"] if row else 0}


@router.get("/pending")
def get_pending(request: Request) -> list[dict]:
    db = request.app.state.db
    rows = get_pending_notifications(db, "player_default")
    return [dict(row) for row in rows]


@router.get("/inbox")
def get_inbox(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    event_type: str | None = Query(default=None),
) -> list[dict]:
    """Return all notifications newest-first (acknowledged and pending).

    Optional `event_type` filter: item_drop, level_up, place_unlock,
    place_level_up, achievement_unlock, challenge_complete.
    Optional `limit` (default 50, max 200).
    """
    db = request.app.state.db
    if event_type is not None:
        rows = db.execute(
            """
            SELECT * FROM pending_notifications
            WHERE character_id='player_default' AND event_type=?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (event_type, limit),
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT * FROM pending_notifications
            WHERE character_id='player_default'
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


@router.post("/{notification_id}/ack")
def ack_notification(notification_id: str, request: Request) -> dict:
    db = request.app.state.db
    result = db.execute(
        "UPDATE pending_notifications SET acknowledged=1 WHERE notification_id=?",
        (notification_id,),
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    db.commit()
    return {"acknowledged": True}


@router.post("/ack-all")
def ack_all_notifications(request: Request) -> dict:
    """Mark all pending notifications for the default player as acknowledged."""
    db = request.app.state.db
    result = db.execute(
        "UPDATE pending_notifications SET acknowledged=1 "
        "WHERE character_id='player_default' AND acknowledged=0"
    )
    db.commit()
    return {"acknowledged_count": result.rowcount}


class AckByTypeBody(BaseModel):
    event_type: str


@router.post("/ack-by-type")
def ack_by_type(body: AckByTypeBody, request: Request) -> dict:
    """Bulk-acknowledge all unread notifications of a specific event_type.

    Useful for dismissing an entire category (e.g. all item_drop notifications).
    Returns 400 if event_type is empty.
    """
    if not body.event_type.strip():
        raise HTTPException(status_code=400, detail="event_type must not be empty")
    db = request.app.state.db
    result = db.execute(
        "UPDATE pending_notifications SET acknowledged=1 "
        "WHERE character_id='player_default' AND event_type=? AND acknowledged=0",
        (body.event_type,),
    )
    db.commit()
    return {"acknowledged_count": result.rowcount, "event_type": body.event_type}
