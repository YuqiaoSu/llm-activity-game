from __future__ import annotations
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from services.models.item import Effect
from services.models.place import Place

_DEFAULT_SET_BONUS_FACTOR = 1.25   # 25 % XP boost when all slots share a category


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


def load_place_perks(conn: sqlite3.Connection) -> list[Effect]:
    """Return synthetic xp_multiplier Effects for all donated place perks.

    Each perk contributes a factor of (1 + boost_factor) to the overall XP
    multiplier.  Multiple perks for the same place stack multiplicatively.
    """
    rows = conn.execute(
        "SELECT place_id, boost_factor FROM place_perks"
    ).fetchall()
    return [
        Effect(
            effect_type="xp_multiplier",
            target=row["place_id"],
            params={"factor": 1.0 + float(row["boost_factor"])},
        )
        for row in rows
    ]


def compute_set_bonuses(conn: sqlite3.Connection) -> list[Effect]:
    """Return synthetic xp_multiplier Effects for places with a category set bonus.

    A place triggers a set bonus when:
    - All of its slots have occupants (no empty slot), AND
    - All occupying items share the same category.

    The multiplier is taken from the place's metadata key ``set_bonus_factor``
    (default: _DEFAULT_SET_BONUS_FACTOR).  The returned Effects have
    effect_type="set_bonus" so the agent can log them distinctly.
    """
    bonuses: list[Effect] = []

    place_rows = conn.execute("SELECT place_id, metadata FROM places").fetchall()
    for place_row in place_rows:
        place_id: str = place_row["place_id"]
        meta: dict = json.loads(place_row["metadata"]) if place_row["metadata"] else {}
        factor: float = float(meta.get("set_bonus_factor", _DEFAULT_SET_BONUS_FACTOR))

        slot_rows = conn.execute(
            "SELECT occupant_id FROM place_slots WHERE place_id=?", (place_id,)
        ).fetchall()

        if not slot_rows:
            continue   # place has no slots — set bonus not applicable

        # Every slot must be filled
        if any(s["occupant_id"] is None for s in slot_rows):
            continue

        # Collect the category of each occupying item
        categories: set[str] = set()
        skip = False
        for slot_row in slot_rows:
            inv = conn.execute(
                "SELECT item_id FROM inventory WHERE instance_id=?",
                (slot_row["occupant_id"],),
            ).fetchone()
            if not inv:
                skip = True
                break
            item = conn.execute(
                "SELECT json_extract(data, '$.category') AS cat FROM item_definitions WHERE item_id=?",
                (inv["item_id"],),
            ).fetchone()
            if not item or not item["cat"]:
                skip = True
                break
            categories.add(item["cat"])

        if skip or len(categories) != 1:
            continue   # mixed categories — no bonus

        bonuses.append(Effect(
            effect_type="set_bonus",
            target=place_id,
            params={"factor": factor, "category": next(iter(categories))},
        ))

    return bonuses
