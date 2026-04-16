import json
import random
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

router = APIRouter()

# Ordered rarity tiers — fusion consumes 3× tier N to produce 1× tier N+1
_RARITY_ORDER = ["COMMON", "UNCOMMON", "RARE", "EPIC", "LEGENDARY"]
_FUSE_COUNT = 3   # copies required to fuse


class EquipRequest(BaseModel):
    equipped: bool


class FuseRequest(BaseModel):
    item_id: str   # the item type to fuse (must have >= 3 unplaced copies)


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
            json_extract(d.data, '$.description')  AS description,
            json_extract(d.data, '$.effects')      AS effects_json,
            c.first_seen_at
        FROM inventory i
        LEFT JOIN item_definitions d ON i.item_id = d.item_id
        LEFT JOIN collection_log c
            ON i.item_id = c.item_id AND c.player_id = 'player_default'
        WHERE i.character_id = 'player_default'
        GROUP BY i.item_id, i.character_id
        ORDER BY last_acquired_at DESC
        """
    ).fetchall()
    import json as _json
    result = []
    for row in rows:
        d = dict(row)
        # Parse effects_json into a list so the client gets structured data
        raw_effects = d.pop("effects_json", None)
        d["effects"] = _json.loads(raw_effects) if raw_effects else []
        d["description"] = d.get("description") or ""
        result.append(d)
    return result


@router.delete("/instances/{instance_id}")
def discard_item(instance_id: str, request: Request) -> dict:
    """Delete a specific item instance from the player's inventory.

    Returns 404 if the instance doesn't exist or belongs to another player.
    Returns 409 if the instance is currently assigned to a place slot.
    """
    db = request.app.state.db
    row = db.execute(
        "SELECT instance_id, placed_in FROM inventory WHERE instance_id=? AND character_id='player_default'",
        (instance_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Item instance not found")
    if row["placed_in"] is not None:
        raise HTTPException(status_code=409, detail="Item is placed in a slot; remove it first")

    db.execute("DELETE FROM inventory WHERE instance_id=?", (instance_id,))
    db.commit()
    return {"deleted": True, "instance_id": instance_id}


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


@router.post("/fuse")
def fuse_items(body: FuseRequest, request: Request) -> dict:
    """Fuse 3 copies of the same item into 1 copy of the next rarity tier.

    Rules:
    - Consumes exactly 3 unplaced (placed_in IS NULL) instances of `item_id`.
    - Equipped instances are included only if no unplaced-unequipped copies exist
      first (prefers spending unequipped copies to minimise disruption).
    - The resulting item is drawn randomly from `item_definitions` at the next
      rarity tier (same or different item_id — it's a fusion reward, not a copy).
    - LEGENDARY items cannot be fused (400).
    - Returns the new item dict plus the consumed instance IDs.
    """
    db = request.app.state.db

    # Resolve current rarity of the item
    def_row = db.execute(
        "SELECT json_extract(data, '$.rarity') AS rarity FROM item_definitions WHERE item_id=?",
        (body.item_id,),
    ).fetchone()
    if def_row is None:
        raise HTTPException(status_code=404, detail="Item definition not found")

    current_rarity: str = def_row["rarity"]
    if current_rarity not in _RARITY_ORDER:
        raise HTTPException(status_code=400, detail=f"Unknown rarity: {current_rarity}")
    rarity_idx = _RARITY_ORDER.index(current_rarity)
    if rarity_idx >= len(_RARITY_ORDER) - 1:
        raise HTTPException(status_code=400, detail="LEGENDARY items cannot be fused")
    next_rarity = _RARITY_ORDER[rarity_idx + 1]

    # Find unplaced instances — prefer unequipped first
    candidates = db.execute(
        """
        SELECT instance_id, equipped
        FROM inventory
        WHERE character_id='player_default' AND item_id=? AND placed_in IS NULL
        ORDER BY equipped ASC   -- 0 (unequipped) first
        LIMIT ?
        """,
        (body.item_id, _FUSE_COUNT),
    ).fetchall()

    if len(candidates) < _FUSE_COUNT:
        raise HTTPException(
            status_code=400,
            detail=f"Need {_FUSE_COUNT} unplaced copies of {body.item_id}; "
                   f"found {len(candidates)}",
        )

    consumed_ids = [r["instance_id"] for r in candidates]

    # Pick a random item at next_rarity
    targets = db.execute(
        "SELECT item_id FROM item_definitions "
        "WHERE json_extract(data, '$.rarity') = ?",
        (next_rarity,),
    ).fetchall()
    if not targets:
        raise HTTPException(
            status_code=500,
            detail=f"No item definitions found for rarity {next_rarity}",
        )
    new_item_id: str = random.choice(targets)["item_id"]

    # Delete consumed instances
    for iid in consumed_ids:
        db.execute("DELETE FROM inventory WHERE instance_id=?", (iid,))

    # Insert new instance
    new_instance_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk) "
        "VALUES (?, 'player_default', ?, ?, 'fusion')",
        (new_instance_id, new_item_id, now),
    )

    # Stamp collection log (INSERT OR IGNORE — first discovery only)
    db.execute(
        "INSERT OR IGNORE INTO collection_log (player_id, item_id, first_seen_at) VALUES (?, ?, ?)",
        ("player_default", new_item_id, now),
    )

    db.commit()

    # Return new item details
    new_def = db.execute(
        "SELECT data FROM item_definitions WHERE item_id=?", (new_item_id,)
    ).fetchone()
    new_item_data = json.loads(new_def["data"]) if new_def else {}
    return {
        "new_instance_id": new_instance_id,
        "new_item_id": new_item_id,
        "new_rarity": next_rarity,
        "new_item": new_item_data,
        "consumed_instance_ids": consumed_ids,
        "fused_from_rarity": current_rarity,
    }
