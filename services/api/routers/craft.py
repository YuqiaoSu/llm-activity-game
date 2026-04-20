"""POST /inventory/craft — combine two items of the same category."""
from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()

_RARITY_ORDER = ["COMMON", "UNCOMMON", "RARE", "EPIC", "LEGENDARY"]


class CraftRequest(BaseModel):
    item_id_a: str
    item_id_b: str


@router.post("")
def craft_items(body: CraftRequest, request: Request) -> dict:
    """Craft two items of the same category into one higher-quality item.

    Rules:
    - item_id_a and item_id_b must be different item types.
    - Both items must belong to the same category.
    - The player must own at least 1 unplaced (placed_in IS NULL) copy of each.
    - The resulting item is drawn randomly from item_definitions in the same
      category at the higher of the two rarities.
    - Returns 400 for same-item-type, category mismatch, or insufficient copies.
    """
    if body.item_id_a == body.item_id_b:
        raise HTTPException(status_code=400, detail="item_id_a and item_id_b must be different")

    db = request.app.state.db

    # Load definitions for both items
    def_a = _get_def(db, body.item_id_a)
    def_b = _get_def(db, body.item_id_b)

    if def_a["category"] != def_b["category"]:
        raise HTTPException(
            status_code=400,
            detail=f"Items must be in the same category "
                   f"(got {def_a['category']} and {def_b['category']})",
        )

    category = def_a["category"]

    # Resolve max rarity
    rarity_a = def_a["rarity"]
    rarity_b = def_b["rarity"]
    idx_a = _RARITY_ORDER.index(rarity_a) if rarity_a in _RARITY_ORDER else 0
    idx_b = _RARITY_ORDER.index(rarity_b) if rarity_b in _RARITY_ORDER else 0
    result_rarity = _RARITY_ORDER[max(idx_a, idx_b)]

    # Find one unplaced copy of each
    inst_a = _find_unplaced(db, body.item_id_a)
    inst_b = _find_unplaced(db, body.item_id_b)

    if inst_a is None:
        raise HTTPException(status_code=400, detail=f"No unplaced copy of {body.item_id_a}")
    if inst_b is None:
        raise HTTPException(status_code=400, detail=f"No unplaced copy of {body.item_id_b}")

    # Pick result item — same category, result_rarity, exclude inputs
    candidates = db.execute(
        """
        SELECT item_id FROM item_definitions
        WHERE json_extract(data, '$.category') = ?
          AND json_extract(data, '$.rarity')   = ?
          AND item_id NOT IN (?, ?)
        """,
        (category, result_rarity, body.item_id_a, body.item_id_b),
    ).fetchall()

    # Fallback: allow same items if no other candidates exist
    if not candidates:
        candidates = db.execute(
            """
            SELECT item_id FROM item_definitions
            WHERE json_extract(data, '$.category') = ?
              AND json_extract(data, '$.rarity')   = ?
            """,
            (category, result_rarity),
        ).fetchall()

    if not candidates:
        raise HTTPException(
            status_code=500,
            detail=f"No item definitions found for category={category} rarity={result_rarity}",
        )

    new_item_id: str = random.choice(candidates)["item_id"]

    # Consume input copies
    db.execute("DELETE FROM inventory WHERE instance_id=?", (inst_a,))
    db.execute("DELETE FROM inventory WHERE instance_id=?", (inst_b,))

    # Insert result
    new_instance_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk) "
        "VALUES (?, 'player_default', ?, ?, 'craft')",
        (new_instance_id, new_item_id, now),
    )

    # Stamp collection log
    db.execute(
        "INSERT OR IGNORE INTO collection_log (player_id, item_id, first_seen_at) VALUES (?, ?, ?)",
        ("player_default", new_item_id, now),
    )

    # Crafting audit log
    db.execute(
        "INSERT INTO crafting_log"
        " (log_id, player_id, action, source_ids, result_item_id, result_rarity, happened_at)"
        " VALUES (?, 'player_default', 'craft', ?, ?, ?, ?)",
        (str(uuid.uuid4()), json.dumps([inst_a, inst_b]), new_item_id, result_rarity, now),
    )

    db.commit()

    new_def_row = db.execute(
        "SELECT data FROM item_definitions WHERE item_id=?", (new_item_id,)
    ).fetchone()
    new_item_data = json.loads(new_def_row["data"]) if new_def_row else {}

    return {
        "new_instance_id": new_instance_id,
        "new_item_id": new_item_id,
        "new_rarity": result_rarity,
        "new_category": category,
        "new_item": new_item_data,
        "consumed_instance_ids": [inst_a, inst_b],
        "crafted_from": [body.item_id_a, body.item_id_b],
    }


def _get_def(db, item_id: str) -> dict:
    row = db.execute(
        "SELECT json_extract(data,'$.rarity') AS rarity, "
        "       json_extract(data,'$.category') AS category "
        "FROM item_definitions WHERE item_id=?",
        (item_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Item definition not found: {item_id}")
    return dict(row)


def _find_unplaced(db, item_id: str) -> str | None:
    row = db.execute(
        "SELECT instance_id FROM inventory "
        "WHERE character_id='player_default' AND item_id=? AND placed_in IS NULL "
        "ORDER BY equipped ASC LIMIT 1",
        (item_id,),
    ).fetchone()
    return row["instance_id"] if row else None
