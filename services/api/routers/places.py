import json
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel, Field
from services.place_service.service import get_place, list_places
from services.place_service.effects import rebuild_active_effects, compute_set_bonuses
from services.place_service.upgrade import award_place_xp, get_place_preferred_category
from services.progression.xp import get_total_xp, deduct_total_xp

_ACTIVITY_PLAYER = "player_default"


def _log_place_activity(db, place_id: str, action: str, amount: int = 0) -> None:
    """Append one row to place_activity_log. Caller is responsible for commit."""
    db.execute(
        "INSERT INTO place_activity_log (log_id, player_id, place_id, action, amount, happened_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), _ACTIVITY_PLAYER, place_id, action, amount,
         datetime.now(timezone.utc).isoformat()),
    )


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


@router.get("/leaderboard")
def get_place_leaderboard(request: Request) -> list[dict]:
    """Return unlocked places ranked by total XP earned (desc)."""
    db = request.app.state.db
    rows = db.execute(
        "SELECT place_id, name, level, xp FROM places WHERE state='UNLOCKED' ORDER BY xp DESC, name ASC"
    ).fetchall()
    return [
        {
            "rank":     idx + 1,
            "place_id": row["place_id"],
            "name":     row["name"],
            "level":    row["level"],
            "xp":       row["xp"],
        }
        for idx, row in enumerate(rows)
    ]


@router.get("/{place_id}/upgrade-preview")
def get_place_upgrade_preview(
    place_id: str,
    request: Request,
    xp: int = Query(default=0, ge=0),
) -> dict:
    """Return a preview of what investing `xp` into a place would achieve.

    Computes the result purely in Python — no DB write.
    Returns 404 if the place does not exist.
    """
    from services.place_service.upgrade import xp_threshold, xp_to_level

    db = request.app.state.db
    row = db.execute("SELECT xp, level FROM places WHERE place_id=?", (place_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Place not found")

    current_xp: int   = int(row["xp"])
    current_level: int = int(row["level"])
    projected_xp: int  = current_xp + xp
    projected_level: int = xp_to_level(projected_xp)
    next_threshold: int  = xp_threshold(projected_level + 1)

    return {
        "place_id":       place_id,
        "current_xp":     current_xp,
        "projected_xp":   projected_xp,
        "current_level":  current_level,
        "projected_level": projected_level,
        "would_level_up": projected_level > current_level,
        "xp_to_next":     max(0, next_threshold - projected_xp),
    }


@router.get("/{place_id}/history")
def get_place_history(
    place_id: str,
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[dict]:
    """Return recent activity events for a place (invest / donate / slot_assign), newest first.

    Returns 404 if the place does not exist.
    """
    db = request.app.state.db
    if db.execute("SELECT 1 FROM places WHERE place_id=?", (place_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="Place not found")
    rows = db.execute(
        "SELECT action, amount, happened_at FROM place_activity_log"
        " WHERE player_id=? AND place_id=?"
        " ORDER BY happened_at DESC LIMIT ?",
        (_ACTIVITY_PLAYER, place_id, limit),
    ).fetchall()
    return [{"action": r["action"], "amount": r["amount"], "happened_at": r["happened_at"]}
            for r in rows]


def _add_preferred_category(place_dicts: list[dict]) -> list[dict]:
    for p in place_dicts:
        p["preferred_category"] = get_place_preferred_category(p.get("place_type", ""))
    return place_dicts


@router.get("")
def get_places(request: Request) -> list[dict]:
    db = request.app.state.db
    dicts = [_enrich_slots(db, p.model_dump()) for p in list_places(db)]
    _add_set_bonus_flag(db, dicts)
    _add_preferred_category(dicts)
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
        # Wear the item slightly on slot-assign
        db.execute(
            "UPDATE inventory SET durability = MAX(0, durability - 10) WHERE instance_id=?",
            (body.instance_id,),
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


_INVEST_DAILY_CAP = 500
_INVEST_PLAYER = "player_default"


class InvestBody(BaseModel):
    xp: int = Field(..., ge=1, description="XP to donate to this place (min 1)")


@router.post("/{place_id}/invest")
def invest_xp(place_id: str, body: InvestBody, request: Request) -> dict:
    """Donate player XP directly to a place, advancing its level progression.

    Deducts `xp` from the player's total XP pool (distributed proportionally
    across categories) and awards it to the place via award_place_xp.

    Returns 404 if the place does not exist.
    Returns 409 if the place is not UNLOCKED.
    Returns 402 if the player does not have enough XP.
    Returns 429 if the daily cap (500 XP per place) would be exceeded.
    """
    from datetime import date
    db = request.app.state.db

    place_row = db.execute(
        "SELECT state, xp, level FROM places WHERE place_id=?", (place_id,)
    ).fetchone()
    if place_row is None:
        raise HTTPException(status_code=404, detail="Place not found")
    if place_row["state"] != "UNLOCKED":
        raise HTTPException(status_code=409, detail="Place is not unlocked")

    today = date.today().isoformat()
    log_row = db.execute(
        "SELECT total_invested FROM place_invest_log WHERE player_id=? AND place_id=? AND invest_date=?",
        (_INVEST_PLAYER, place_id, today),
    ).fetchone()
    invested_today = int(log_row["total_invested"]) if log_row else 0
    remaining_cap = _INVEST_DAILY_CAP - invested_today
    if body.xp > remaining_cap:
        raise HTTPException(
            status_code=429,
            detail={
                "message": f"Daily cap of {_INVEST_DAILY_CAP} XP per place would be exceeded",
                "invested_today": invested_today,
                "cap": _INVEST_DAILY_CAP,
                "remaining": remaining_cap,
            },
        )

    total_xp = get_total_xp(db, _INVEST_PLAYER)
    if total_xp < body.xp:
        raise HTTPException(
            status_code=402,
            detail=f"Insufficient XP: have {total_xp}, need {body.xp}",
        )

    deduct_total_xp(db, _INVEST_PLAYER, body.xp)
    levelled_up = award_place_xp(db, place_id, body.xp)

    # Upsert today's invest log
    db.execute(
        """
        INSERT INTO place_invest_log (player_id, place_id, invest_date, total_invested)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (player_id, place_id, invest_date)
        DO UPDATE SET total_invested = total_invested + excluded.total_invested
        """,
        (_INVEST_PLAYER, place_id, today, body.xp),
    )
    _log_place_activity(db, place_id, "invest", body.xp)
    db.commit()

    invested_today += body.xp
    updated = db.execute(
        "SELECT xp, level FROM places WHERE place_id=?", (place_id,)
    ).fetchone()
    return {
        "place_id":       place_id,
        "xp_invested":    body.xp,
        "new_xp":         updated["xp"],
        "new_level":      updated["level"],
        "levelled_up":    levelled_up,
        "invested_today": invested_today,
        "cap":            _INVEST_DAILY_CAP,
        "remaining":      _INVEST_DAILY_CAP - invested_today,
    }


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

    # Consume the item (durability decremented implicitly by deletion — item is gone)
    db.execute("DELETE FROM inventory WHERE instance_id=?", (body.instance_id,))

    # Write perk
    now = datetime.now(timezone.utc).isoformat()
    perk_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO place_perks (perk_id, place_id, item_id, instance_id, boost_factor, donated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (perk_id, place_id, item_id, body.instance_id, _DEFAULT_BOOST_FACTOR, now),
    )
    _log_place_activity(db, place_id, "donate")
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


_GIFT_XP: dict[str, int] = {
    "COMMON": 5,
    "UNCOMMON": 15,
    "RARE": 30,
    "EPIC": 60,
    "LEGENDARY": 100,
}


class GiftItemBody(BaseModel):
    instance_id: str


@router.post("/{place_id}/gift-item")
def gift_item(place_id: str, body: GiftItemBody, request: Request) -> dict:
    """Convert an inventory item directly into place XP (one-shot, no perk created).

    XP awarded by rarity: COMMON=5, UNCOMMON=15, RARE=30, EPIC=60, LEGENDARY=100.
    The item instance is consumed from inventory.

    Returns 404 if the place or item instance is not found.
    Returns 409 if the instance is locked or the place is not UNLOCKED.
    """
    db = request.app.state.db

    place_row = db.execute(
        "SELECT state, xp, level FROM places WHERE place_id=?", (place_id,)
    ).fetchone()
    if place_row is None:
        raise HTTPException(status_code=404, detail="Place not found")
    if place_row["state"] != "UNLOCKED":
        raise HTTPException(status_code=409, detail="Place is not unlocked")

    inv_row = db.execute(
        """
        SELECT i.instance_id, i.item_id, i.locked,
               json_extract(d.data, '$.rarity')   AS rarity,
               json_extract(d.data, '$.category') AS category
        FROM inventory i
        JOIN item_definitions d ON i.item_id = d.item_id
        WHERE i.instance_id=? AND i.character_id='player_default'
        """,
        (body.instance_id,),
    ).fetchone()
    if inv_row is None:
        raise HTTPException(status_code=404, detail="Item instance not found in inventory")
    if int(inv_row["locked"]):
        raise HTTPException(status_code=409, detail="Item is locked; unlock it before gifting")

    rarity: str = inv_row["rarity"] or "COMMON"
    item_category: str | None = inv_row["category"]
    xp_gained: int = _GIFT_XP.get(rarity, 5)

    db.execute("DELETE FROM inventory WHERE instance_id=?", (body.instance_id,))
    levelled_up = award_place_xp(db, place_id, xp_gained, chunk_category=item_category)
    _log_place_activity(db, place_id, "gift_item", xp_gained)
    db.commit()

    updated = db.execute(
        "SELECT xp, level, place_type FROM places WHERE place_id=?", (place_id,)
    ).fetchone()
    preferred = get_place_preferred_category(updated["place_type"] or "")
    specialty = bool(preferred and item_category and preferred.upper() == item_category.upper())
    return {
        "place_id":        place_id,
        "instance_id":     body.instance_id,
        "rarity":          rarity,
        "xp_gained":       xp_gained,
        "new_place_xp":    updated["xp"],
        "new_place_level": updated["level"],
        "levelled_up":     levelled_up,
        "specialty_bonus": specialty,
    }
