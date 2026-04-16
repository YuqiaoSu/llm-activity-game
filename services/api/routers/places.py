import json
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from services.place_service.service import get_place, list_places
from services.place_service.effects import rebuild_active_effects, compute_set_bonuses


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
    return _add_set_bonus_flag(db, dicts)


@router.get("/{place_id}")
def get_place_by_id(place_id: str, request: Request) -> dict:
    db = request.app.state.db
    place = get_place(db, place_id)
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")
    result = _enrich_slots(db, place.model_dump())
    return _add_set_bonus_flag(db, [result])[0]


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
