from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

router = APIRouter()


class EquipRequest(BaseModel):
    equipped: bool


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
            MIN(CASE WHEN i.placed_in IS NULL THEN i.instance_id ELSE NULL END)
                                                   AS available_instance_id,
            json_extract(d.data, '$.name')         AS name,
            json_extract(d.data, '$.rarity')       AS rarity,
            json_extract(d.data, '$.category')     AS category,
            json_extract(d.data, '$.icon')         AS icon,
            json_extract(d.data, '$.effects')      AS effects_json
        FROM inventory i
        LEFT JOIN item_definitions d ON i.item_id = d.item_id
        WHERE i.character_id = 'player_default'
        GROUP BY i.item_id, i.character_id
        ORDER BY last_acquired_at DESC
        """
    ).fetchall()
    import json
    result = []
    for row in rows:
        d = dict(row)
        # Parse effects_json into a list so the client gets structured data
        raw_effects = d.pop("effects_json", None)
        d["effects"] = json.loads(raw_effects) if raw_effects else []
        result.append(d)
    return result


@router.patch("/{item_id}/equip")
def equip_item(item_id: str, body: EquipRequest, request: Request) -> dict:
    """Toggle the equipped flag for all instances of item_id owned by the player.

    Idempotent: equipping an already-equipped item returns 200 with no DB change.
    Returns 404 if the player does not own this item.
    """
    db = request.app.state.db
    row = db.execute(
        "SELECT COUNT(*) AS cnt FROM inventory WHERE character_id='player_default' AND item_id=?",
        (item_id,),
    ).fetchone()
    if row["cnt"] == 0:
        raise HTTPException(status_code=404, detail="Item not in inventory")

    db.execute(
        "UPDATE inventory SET equipped=? WHERE character_id='player_default' AND item_id=?",
        (1 if body.equipped else 0, item_id),
    )
    db.commit()
    return {"item_id": item_id, "equipped": body.equipped, "quantity": row["cnt"]}
