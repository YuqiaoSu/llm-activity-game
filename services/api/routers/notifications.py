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
