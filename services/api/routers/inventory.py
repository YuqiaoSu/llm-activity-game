from fastapi import APIRouter, Request

router = APIRouter()


@router.get("")
def get_inventory(request: Request) -> list[dict]:
    db = request.app.state.db
    rows = db.execute(
        """
        SELECT
            i.instance_id, i.character_id, i.item_id,
            i.acquired_at, i.source_chunk, i.equipped, i.placed_in,
            json_extract(d.data, '$.name')     AS name,
            json_extract(d.data, '$.rarity')   AS rarity,
            json_extract(d.data, '$.category') AS category,
            json_extract(d.data, '$.icon')     AS icon
        FROM inventory i
        LEFT JOIN item_definitions d ON i.item_id = d.item_id
        WHERE i.character_id = 'player_default'
        ORDER BY i.acquired_at DESC
        """
    ).fetchall()
    return [dict(row) for row in rows]
