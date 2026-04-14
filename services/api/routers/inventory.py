from fastapi import APIRouter, Request

router = APIRouter()


@router.get("")
def get_inventory(request: Request) -> list[dict]:
    db = request.app.state.db
    rows = db.execute(
        "SELECT * FROM inventory WHERE character_id='player_default' ORDER BY acquired_at DESC"
    ).fetchall()
    return [dict(row) for row in rows]
