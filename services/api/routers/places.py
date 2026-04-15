from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from services.place_service.service import get_place, list_places
from services.place_service.effects import rebuild_active_effects

router = APIRouter()


class SlotAssignBody(BaseModel):
    instance_id: str | None  # None = remove occupant


@router.get("")
def get_places(request: Request) -> list[dict]:
    db = request.app.state.db
    places = list_places(db)
    return [p.model_dump() for p in places]


@router.get("/{place_id}")
def get_place_by_id(place_id: str, request: Request) -> dict:
    db = request.app.state.db
    place = get_place(db, place_id)
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")
    return place.model_dump()


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
            "SELECT instance_id FROM inventory WHERE instance_id=? AND character_id='player_default'",
            (body.instance_id,),
        ).fetchone()
        if inv_row is None:
            raise HTTPException(status_code=404, detail="Item instance not found in inventory")
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
