from fastapi import APIRouter, Request, HTTPException, Query
from services.reward_ledger.ledger import get_pending_notifications

router = APIRouter()


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
    achievement_unlock, challenge_complete.
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
    """Mark all pending notifications for the default player as acknowledged.

    Called on first launch to avoid flooding the overlay with historical drops.
    """
    db = request.app.state.db
    result = db.execute(
        "UPDATE pending_notifications SET acknowledged=1 "
        "WHERE character_id='player_default' AND acknowledged=0"
    )
    db.commit()
    return {"acknowledged_count": result.rowcount}
