import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from services.place_service.service import get_place, list_places
from services.place_service.effects import rebuild_active_effects, compute_set_bonuses

_MIN_PLACE_LEVEL_FOR_DONATION = 5
_DEFAULT_BOOST_FACTOR = 0.10   # 10% additive XP multiplier per donated item


def _accepts_list(slot: dict) -> list[str]:
    """Return the slot's accepts list (upper-cased), or [] if no filter."""
    raw = slot.get("accepts")
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(a).upper() for a in raw]
    # stored as JSON string in some paths
    try:
        parsed = json.loads(raw)
        return [str(a).upper() for a in parsed] if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []

router = APIRouter()


class SlotAssignBody(BaseModel):
    instance_id: str | None  # None = remove occupant


def _enrich_slots(db, place_dict: dict) -> dict:
    """Add occupant_name, occupant_rarity, occupant_category, and occupant_matches_theme
    to each slot that has an occupant_id."""
    for slot in place_dict.get("slots", []):
        occupant_id = slot.get("occupant_id")
        accepts = _accepts_list(slot)
        if occupant_id is None:
            slot["occupant_name"] = None
            slot["occupant_rarity"] = None
            slot["occupant_category"] = None
            slot["occupant_matches_theme"] = False
            continue
        row = db.execute(
            """
            SELECT json_extract(d.data, '$.name')     AS name,
                   json_extract(d.data, '$.rarity')   AS rarity,
                   json_extract(d.data, '$.category') AS category
            FROM inventory i
            JOIN item_definitions d ON i.item_id = d.item_id
            WHERE i.instance_id = ?
            """,
            (occupant_id,),
        ).fetchone()
        slot["occupant_name"]   = row["name"]     if row else None
        slot["occupant_rarity"] = row["rarity"]   if row else None
        slot["occupant_category"] = row["category"] if row else None
        if accepts and row and row["category"]:
            slot["occupant_matches_theme"] = row["category"].upper() in accepts
        else:
            slot["occupant_matches_theme"] = not bool(accepts)  # True when no filter
    return place_dict


def _add_perks(db, place_dicts: list[dict]) -> list[dict]:
    """Attach a `perks` list to each place dict from the place_perks table.

    Each perk entry: {perk_id, item_id, item_name, item_rarity, boost_factor, donated_at}.
    Places with no perks get an empty list.
    """
    # Fetch all perks joined with item_definitions in one query
    rows = db.execute(
        """
        SELECT p.perk_id, p.place_id, p.item_id, p.boost_factor, p.donated_at,
               json_extract(d.data, '$.name')   AS item_name,
               json_extract(d.data, '$.rarity') AS item_rarity
        FROM place_perks p
        LEFT JOIN item_definitions d ON p.item_id = d.item_id
        ORDER BY p.donated_at
        """
    ).fetchall()

    # Group by place_id
    by_place: dict[str, list[dict]] = {}
    for r in rows:
        entry = {
            "perk_id":     r["perk_id"],
            "item_id":     r["item_id"],
            "item_name":   r["item_name"] or r["item_id"],
            "item_rarity": r["item_rarity"],
            "boost_factor": float(r["boost_factor"]),
            "donated_at":  r["donated_at"],
        }
        by_place.setdefault(r["place_id"], []).append(entry)

    for p in place_dicts:
        p["perks"] = by_place.get(p.get("place_id", ""), [])
    return place_dicts


def _add_set_bonus_flag(db, place_dicts: list[dict]) -> list[dict]:
    """Annotate each place dict with set_bonus_active and set_bonus_factor."""
    bonuses = compute_set_bonuses(db)
    active_place_ids = {e.target for e in bonuses}
    bonus_factors = {e.target: e.params.get("factor", 1.25) for e in bonuses}
    for p in place_dicts:
        pid = p.get("place_id", "")
        p["set_bonus_active"] = pid in active_place_ids
        p["set_bonus_factor"] = bonus_factors.get(pid, None)
    return place_dicts


@router.get("")
def get_places(request: Request) -> list[dict]:
    db = request.app.state.db
    dicts = [_enrich_slots(db, p.model_dump()) for p in list_places(db)]
    _add_set_bonus_flag(db, dicts)
    return _add_perks(db, dicts)


@router.get("/{place_id}")
def get_place_by_id(place_id: str, request: Request) -> dict:
    db = request.app.state.db
    place = get_place(db, place_id)
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")
    result = _enrich_slots(db, place.model_dump())
    _add_set_bonus_flag(db, [result])
    return _add_perks(db, [result])[0]


@router.put("/{place_id}/slots/{slot_id}")
def assign_slot(place_id: str, slot_id: str, body: SlotAssignBody, request: Request) -> dict:
    """Assign or remove an item instance from a place slot.

    - Validates the slot belongs to the place.
    - If assigning (instance_id not None), validates the item is in the player's inventory.
    - Clears `placed_in` on the previous occupant (if any) before assigning the new one.
    - Updates `placed_in` on the new occupant.
    - Rebuilds `place_active_effects` for the place.
    """
    db = request.app.state.db

    # Validate slot belongs to this place
    slot_row = db.execute(
        "SELECT * FROM place_slots WHERE slot_id=? AND place_id=?",
        (slot_id, place_id),
    ).fetchone()
    if slot_row is None:
        raise HTTPException(status_code=404, detail="Slot not found on this place")

    # Clear previous occupant's placed_in
    prev_occupant = slot_row["occupant_id"]
    if prev_occupant is not None:
        db.execute("UPDATE inventory SET placed_in=NULL WHERE instance_id=?", (prev_occupant,))

    # Validate new occupant exists in inventory
    if body.instance_id is not None:
        inv_row = db.execute(
            """
            SELECT i.instance_id,
                   json_extract(d.data, '$.category') AS category
            FROM inventory i
            JOIN item_definitions d ON i.item_id = d.item_id
            WHERE i.instance_id=? AND i.character_id='player_default'
            """,
            (body.instance_id,),
        ).fetchone()
        if inv_row is None:
            raise HTTPException(status_code=404, detail="Item instance not found in inventory")

        # Validate category against slot's accepts filter
        slot_data = {"accepts": json.loads(slot_row["accepts"]) if slot_row["accepts"] else None}
        accepts = _accepts_list(slot_data)
        if accepts and inv_row["category"] and inv_row["category"].upper() not in accepts:
            raise HTTPException(
                status_code=400,
                detail=f"Item category '{inv_row['category']}' is not accepted by this slot. "
                       f"Accepted: {', '.join(accepts)}",
            )

        db.execute(
            "UPDATE inventory SET placed_in=? WHERE instance_id=?",
            (slot_id, body.instance_id),
        )

    # Update slot occupant
    db.execute(
        "UPDATE place_slots SET occupant_id=? WHERE slot_id=?",
        (body.instance_id, slot_id),
    )
    db.commit()

    # Rebuild active effects and return updated place
    place = get_place(db, place_id)
    rebuild_active_effects(db, place)
    return get_place(db, place_id).model_dump()


class DonateBody(BaseModel):
    instance_id: str


@router.post("/{place_id}/donate")
def donate_item(place_id: str, body: DonateBody, request: Request) -> dict:
    """Donate an item to a place, permanently granting a +10% XP perk.

    Requirements:
    - Place must be UNLOCKED and at level >= 5.
    - The item instance must exist in the player's inventory and must not be
      placed in a slot (placed_in IS NULL).
    - The same item type (item_id) cannot be donated to the same place twice.

    The item instance is consumed. The perk persists across slot changes.
    """
    db = request.app.state.db

    # Validate place
    place_row = db.execute(
        "SELECT state, level FROM places WHERE place_id=?", (place_id,)
    ).fetchone()
    if place_row is None:
        raise HTTPException(status_code=404, detail="Place not found")
    if place_row["state"] != "UNLOCKED":
        raise HTTPException(status_code=400, detail="Place is not unlocked")
    if int(place_row["level"]) < _MIN_PLACE_LEVEL_FOR_DONATION:
        raise HTTPException(
            status_code=400,
            detail=f"Place must be at least level {_MIN_PLACE_LEVEL_FOR_DONATION} to accept donations "
                   f"(currently level {place_row['level']})",
        )

    # Validate item instance
    inv_row = db.execute(
        "SELECT item_id, placed_in FROM inventory WHERE instance_id=? AND character_id='player_default'",
        (body.instance_id,),
    ).fetchone()
    if inv_row is None:
        raise HTTPException(status_code=404, detail="Item instance not found in inventory")
    if inv_row["placed_in"] is not None:
        raise HTTPException(status_code=400, detail="Item is currently placed in a slot; unplace it first")

    item_id: str = inv_row["item_id"]

    # Prevent donating the same item type twice to the same place
    existing = db.execute(
        "SELECT 1 FROM place_perks WHERE place_id=? AND item_id=?",
        (place_id, item_id),
    ).fetchone()
    if existing:
        raise HTTPException(status_code=409, detail="This item type has already been donated to this place")

    # Consume the item
    db.execute("DELETE FROM inventory WHERE instance_id=?", (body.instance_id,))

    # Write perk
    now = datetime.now(timezone.utc).isoformat()
    perk_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO place_perks (perk_id, place_id, item_id, instance_id, boost_factor, donated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (perk_id, place_id, item_id, body.instance_id, _DEFAULT_BOOST_FACTOR, now),
    )
    db.commit()

    item_row = db.execute(
        "SELECT json_extract(data, '$.name') AS name, "
        "       json_extract(data, '$.rarity') AS rarity "
        "FROM item_definitions WHERE item_id=?",
        (item_id,),
    ).fetchone()

    return {
        "perk_id": perk_id,
        "place_id": place_id,
        "item_id": item_id,
        "item_name": item_row["name"] if item_row else item_id,
        "item_rarity": item_row["rarity"] if item_row else None,
        "boost_factor": _DEFAULT_BOOST_FACTOR,
        "donated_at": now,
    }
