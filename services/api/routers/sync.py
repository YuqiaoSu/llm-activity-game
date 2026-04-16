import httpx
from fastapi import APIRouter, Request, HTTPException

router = APIRouter()


@router.get("/status")
def get_sync_status(request: Request) -> dict:
    db = request.app.state.db
    row = db.execute("SELECT * FROM sync_state WHERE player_id='default'").fetchone()
    if row:
        return {"last_cursor": row["last_cursor"], "last_sync_at": row["last_sync_at"]}
    return {"last_cursor": None, "last_sync_at": None}


@router.post("/poll-now")
def poll_now(request: Request) -> dict:
    try:
        summary = request.app.state.sync_agent.poll_with_summary(manual=True)
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Tracker unavailable")
    return summary
