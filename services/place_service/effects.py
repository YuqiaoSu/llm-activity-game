from __future__ import annotations
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from services.models.item import Effect
from services.models.place import Place


def load_active_effects(conn: sqlite3.Connection) -> list[Effect]:
    """Return all active effects currently applied across all places."""
    rows = conn.execute(
        "SELECT effect_type, params FROM place_active_effects"
    ).fetchall()
    return [Effect(effect_type=r["effect_type"], target="", params=json.loads(r["params"])) for r in rows]


def rebuild_active_effects(conn: sqlite3.Connection, place: Place) -> list[Effect]:
    """
    Delete all active effects for `place`, then re-derive them from occupied slots.
    An occupied slot contributes the equipped item's effects.
    Returns the new list of active effects.
    """
    conn.execute(
        "DELETE FROM place_active_effects WHERE place_id=?", (place.place_id,)
    )

    active: list[Effect] = []
    now = datetime.now(timezone.utc).isoformat()

    for slot in place.slots:
        if slot.occupant_id is None:
            continue
        inv_row = conn.execute(
            "SELECT item_id FROM inventory WHERE instance_id=?", (slot.occupant_id,)
        ).fetchone()
        if not inv_row:
            continue
        item_row = conn.execute(
            "SELECT data FROM item_definitions WHERE item_id=?", (inv_row["item_id"],)
        ).fetchone()
        if not item_row:
            continue
        item_data = json.loads(item_row["data"])
        for effect_dict in item_data.get("effects", []):
            effect = Effect(**effect_dict)
            effect_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO place_active_effects
                    (effect_id, place_id, source_slot_id, effect_type, params, applied_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (effect_id, place.place_id, slot.slot_id,
                 effect.effect_type, json.dumps(effect.params), now),
            )
            active.append(effect)

    conn.commit()
    return active
