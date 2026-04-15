from fastapi import APIRouter, Request, HTTPException
from services.reward_ledger.ledger import get_pending_notifications

router = APIRouter()


@router.get("/pending")
def get_pending(request: Request) -> list[dict]:
    db = request.app.state.db
    rows = get_pending_notifications(db, "player_default")
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
