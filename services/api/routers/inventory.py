from fastapi import APIRouter, Request

router = APIRouter()


@router.get("")
def get_inventory(request: Request) -> list[dict]:
    """Return inventory grouped by item_id with a quantity count.

    Each entry represents one distinct item type owned by the player,
    with `quantity` showing how many copies they hold.
    """
    db = request.app.state.db
    rows = db.execute(
        """
        SELECT
            i.item_id,
            i.character_id,
            COUNT(*)                               AS quantity,
            MAX(i.acquired_at)                     AS last_acquired_at,
            MAX(CASE WHEN i.equipped THEN 1 ELSE 0 END) AS equipped,
            json_extract(d.data, '$.name')         AS name,
            json_extract(d.data, '$.rarity')       AS rarity,
            json_extract(d.data, '$.category')     AS category,
            json_extract(d.data, '$.icon')         AS icon
        FROM inventory i
        LEFT JOIN item_definitions d ON i.item_id = d.item_id
        WHERE i.character_id = 'player_default'
        GROUP BY i.item_id, i.character_id
        ORDER BY last_acquired_at DESC
        """
    ).fetchall()
    return [dict(row) for row in rows]
