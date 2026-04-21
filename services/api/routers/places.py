"""Place management API.

Places are persistent game locations that players unlock, visit, and invest in.
Each place has typed slots that can hold inventory items, granting passive effects
and XP bonuses while occupied.

Key endpoints:
  GET  /places                       — list all places with enriched slot/perk data
  GET  /places/{id}                  — single place detail
  PUT  /places/{id}/slots/{slot_id}  — assign or remove an item from a slot
  POST /places/{id}/visit            — record a visit and award streak rewards
  POST /places/{id}/invest           — spend XP to invest in a place
  POST /places/{id}/donate           — donate an item as a permanent perk
  POST /places/{id}/gift-item        — send a gift item to a place
  GET  /places/{id}/slot-recommend   — best available item per empty slot
  GET  /places/{id}/upgrade-preview  — cost/benefit preview before upgrading
  GET  /places/leaderboard           — places ranked by total XP earned
"""
import json
import random
import uuid
from datetime import datetime, timezone, date as date_type
from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel, Field
from services.place_service.service import get_place, list_places
from services.place_service.effects import rebuild_active_effects, compute_set_bonuses
from services.place_service.upgrade import award_place_xp, get_place_preferred_category, xp_to_level
from services.progression.xp import get_total_xp, deduct_total_xp
from services.reward_ledger.ledger import record_drop, _insert_notification
from services.models.item import ItemDefinition, DropRequirement
from services.models.enums import Category, Rarity

_STREAK_MILESTONES = {3, 7, 14}

_ACTIVITY_PLAYER = "player_default"


def _log_place_activity(db, place_id: str, action: str, amount: int = 0) -> None:
    """Append one row to place_activity_log. Caller is responsible for commit."""
    db.execute(
        "INSERT INTO place_activity_log (log_id, player_id, place_id, action, amount, happened_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), _ACTIVITY_PLAYER, place_id, action, amount,
         datetime.now(timezone.utc).isoformat()),
    )


def _log_slot_assignment(
    db,
    place_id: str,
    slot_id: str,
    action: str,
    item_id: str | None = None,
    instance_id: str | None = None,
) -> None:
    """Append one row to slot_assignment_log. Caller is responsible for commit."""
    db.execute(
        "INSERT INTO slot_assignment_log"
        " (log_id, place_id, slot_id, action, item_id, instance_id, occurred_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            str(uuid.uuid4()),
            place_id,
            slot_id,
            action,
            item_id,
            instance_id,
            datetime.now(timezone.utc).isoformat(),
        ),
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


_RARITY_RANK = {"COMMON": 1, "UNCOMMON": 2, "RARE": 3, "EPIC": 4, "LEGENDARY": 5}


@router.get("/{place_id}/slot-recommend")
def get_slot_recommendations(
    place_id: str, request: Request, locked_only: bool = False
) -> list[dict]:
    """Return the best available unplaced item for each empty slot at this place.

    Scoring: category_match (0 or 10) + rarity_rank (1-5).
    Returns an empty list when all slots are filled or inventory is empty.
    When locked_only=true, only locked items are considered as candidates.
    """
    db = request.app.state.db
    place = db.execute("SELECT place_id FROM places WHERE place_id=?", (place_id,)).fetchone()
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")

    # Load empty slots
    empty_slots = db.execute(
        "SELECT slot_id, slot_type, accepts FROM place_slots"
        " WHERE place_id=? AND occupant_id IS NULL",
        (place_id,),
    ).fetchall()
    if not empty_slots:
        return []

    # Load unplaced inventory items; optionally restrict to locked items
    locked_clause = "AND i.locked = 1" if locked_only else ""
    inv_rows = db.execute(
        f"""
        SELECT i.instance_id,
               json_extract(d.data, '$.name')   AS item_name,
               json_extract(d.data, '$.rarity') AS rarity,
               json_extract(d.data, '$.category') AS category,
               i.locked
        FROM inventory i
        JOIN item_definitions d ON d.item_id = i.item_id
        WHERE i.character_id = 'player_default'
          AND (i.expires_at IS NULL OR i.expires_at > datetime('now'))
          AND i.instance_id NOT IN (
              SELECT occupant_id FROM place_slots WHERE occupant_id IS NOT NULL
          )
          {locked_clause}
        """,
    ).fetchall()
    if not inv_rows:
        return []

    results = []
    for slot in empty_slots:
        slot_id: str = slot["slot_id"]
        accepts = _accepts_list(dict(slot))

        best = None
        best_score = -1
        for item in inv_rows:
            cat: str   = str(item["category"] or "").upper()
            rar: str   = str(item["rarity"] or "COMMON").upper()
            cat_match  = 10 if (not accepts or cat in accepts) else 0
            # Skip items that don't match the slot filter
            if accepts and cat not in accepts:
                continue
            score = cat_match + _RARITY_RANK.get(rar, 1)
            if score > best_score:
                best_score = score
                best = {"slot_id": slot_id, "recommended_instance_id": item["instance_id"],
                        "item_name": item["item_name"], "item_rarity": rar, "score": score}

        if best:
            results.append(best)

    return results


@router.get("/{place_id}/slot-stats")
def get_place_slot_stats(place_id: str, request: Request) -> dict:
    """Return slot fill and category-match statistics for a place."""
    db = request.app.state.db
    place_row = db.execute(
        "SELECT place_id, place_type FROM places WHERE place_id=?", (place_id,)
    ).fetchone()
    if place_row is None:
        raise HTTPException(status_code=404, detail="Place not found")

    slots = db.execute(
        "SELECT slot_id, occupant_id FROM place_slots WHERE place_id=?", (place_id,)
    ).fetchall()
    total_slots = len(slots)
    filled_slots = sum(1 for s in slots if s["occupant_id"] is not None)
    empty_slots = total_slots - filled_slots
    fill_pct = round(filled_slots / total_slots * 100, 1) if total_slots else 0.0

    preferred = get_place_preferred_category(place_row["place_type"])
    matching = 0
    if preferred and filled_slots:
        rows = db.execute(
            """
            SELECT json_extract(d.data, '$.category') AS cat
            FROM place_slots ps
            JOIN inventory i ON ps.occupant_id = i.instance_id
            JOIN item_definitions d ON i.item_id = d.item_id
            WHERE ps.place_id = ? AND ps.occupant_id IS NOT NULL
            """,
            (place_id,),
        ).fetchall()
        matching = sum(1 for r in rows if r["cat"] and r["cat"].upper() == preferred.upper())
    matching_pct = round(matching / filled_slots * 100, 1) if filled_slots else 0.0

    return {
        "total_slots": total_slots,
        "filled_slots": filled_slots,
        "empty_slots": empty_slots,
        "fill_pct": fill_pct,
        "matching_pct": matching_pct,
    }


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
    """Annotate each place dict with a ``preferred_category`` field derived from its place_type."""
    for p in place_dicts:
        p["preferred_category"] = get_place_preferred_category(p.get("place_type", ""))
    return place_dicts


def _add_unlock_progress(db, place_dicts: list[dict]) -> list[dict]:
    """Annotate each locked place with ``unlock_progress`` (current_level, required_level, pct).

    Only ``player_level`` unlock conditions are supported; all others get ``unlock_progress=None``.
    Unlocked places also get ``unlock_progress=None`` — the field is only meaningful when locked.
    """
    player_xp = get_total_xp(db, "player_default")
    player_level = xp_to_level(player_xp)
    for p in place_dicts:
        cond = p.get("unlock_condition")
        if cond and isinstance(cond, dict) and cond.get("condition_type") == "player_level":
            required = int(cond.get("params", {}).get("min_level", 1))
            pct = min(100, int(player_level / required * 100)) if required > 0 else 100
            p["unlock_progress"] = {
                "current_level": player_level,
                "required_level": required,
                "pct": pct,
            }
        else:
            p["unlock_progress"] = None
    return place_dicts


def _add_days_since_visit(place_dicts: list[dict]) -> list[dict]:
    """Annotate each place dict with ``days_since_visit`` (int or None if never visited)."""
    today = date_type.today().isoformat()
    for p in place_dicts:
        lv = p.get("last_visit_date")
        if lv:
            try:
                delta = date_type.fromisoformat(today) - date_type.fromisoformat(lv)
                p["days_since_visit"] = delta.days
            except ValueError:
                p["days_since_visit"] = None
        else:
            p["days_since_visit"] = None
    return place_dicts


@router.get("")
def get_places(request: Request) -> list[dict]:
    """Return all places enriched with slot occupants, perks, set-bonus flags,
    preferred category, days since last visit, and unlock progress."""
    db = request.app.state.db
    dicts = [_enrich_slots(db, p.model_dump()) for p in list_places(db)]
    _add_set_bonus_flag(db, dicts)
    _add_preferred_category(dicts)
    _add_days_since_visit(dicts)
    _add_unlock_progress(db, dicts)
    return _add_perks(db, dicts)


@router.get("/{place_id}")
def get_place_by_id(place_id: str, request: Request) -> dict:
    """Return a single place enriched with slot occupants, perks, and set-bonus flags.

    Raises 404 if *place_id* does not exist.
    """
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

    # Log the previous occupant removal (if any)
    if prev_occupant is not None:
        _log_slot_assignment(db, place_id, slot_id, "removed")

    # Log the new assignment (if any)
    if body.instance_id is not None:
        item_id_row = db.execute(
            "SELECT item_id FROM inventory WHERE instance_id=?", (body.instance_id,)
        ).fetchone()
        _log_slot_assignment(
            db, place_id, slot_id, "assigned",
            item_id=item_id_row["item_id"] if item_id_row else None,
            instance_id=body.instance_id,
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


@router.post("/{place_id}/visit")
def record_visit(place_id: str, request: Request) -> dict:
    """Record that the player visited (opened) this place and update the visit streak.

    Streak logic: same calendar day → no change; +1 day → increment; >1 day → reset to 1.
    Returns 404 if the place does not exist.
    """
    db = request.app.state.db
    place_row = db.execute(
        "SELECT place_id, visit_streak, last_visit_date FROM places WHERE place_id=?",
        (place_id,),
    ).fetchone()
    if place_row is None:
        raise HTTPException(status_code=404, detail="Place not found")

    today = date_type.today()
    today_str = today.isoformat()
    last_visit_date_str = place_row["last_visit_date"]
    current_streak: int = place_row["visit_streak"] or 0

    if last_visit_date_str is None:
        new_streak = 1
    else:
        last_date = date_type.fromisoformat(last_visit_date_str)
        delta = (today - last_date).days
        if delta == 0:
            new_streak = current_streak  # same day — no change
        elif delta == 1:
            new_streak = current_streak + 1
        else:
            new_streak = 1  # gap — reset

    db.execute(
        "UPDATE places SET visit_streak=?, last_visit_date=? WHERE place_id=?",
        (new_streak, today_str, place_id),
    )

    log_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO place_visit_log (log_id, place_id, visited_at) VALUES (?, ?, ?)",
        (log_id, place_id, now_iso),
    )
    db.commit()

    # Milestone streak reward (idempotent via reward_ledger chunk_id)
    reward_item_id: str | None = None
    if new_streak in _STREAK_MILESTONES:
        chunk_id = f"place_streak_{place_id}_{new_streak}"
        item_row = db.execute(
            "SELECT item_id, data FROM item_definitions ORDER BY RANDOM() LIMIT 1"
        ).fetchone()
        if item_row:
            raw = json.loads(item_row["data"])
            try:
                dr_raw = raw.get("drop_requirement")
                dr = DropRequirement(**dr_raw) if isinstance(dr_raw, dict) else DropRequirement()
                item_def = ItemDefinition(
                    item_id=item_row["item_id"],
                    name=raw.get("name", item_row["item_id"]),
                    category=Category(raw.get("category", "GENERAL")),
                    rarity=Rarity(raw.get("rarity", "COMMON")),
                    drop_requirement=dr,
                    icon=raw.get("icon", ""),
                    description=raw.get("description", ""),
                )
            except Exception:
                item_def = None
            if item_def is not None:
                awarded = record_drop(db, chunk_id, 0, item_def, "player_default")
                if awarded:
                    reward_item_id = item_def.item_id
                    _insert_notification(db, "player_default", "place_streak_reward", {
                        "place_id": place_id,
                        "streak_days": new_streak,
                        "item_id": item_def.item_id,
                        "item_name": item_def.name,
                    })
                    db.commit()

    response: dict = {"log_id": log_id, "place_id": place_id, "visited_at": now_iso,
                      "streak_days": new_streak}
    if reward_item_id is not None:
        response["reward_item_id"] = reward_item_id
    return response


@router.get("/{place_id}/visits")
def get_visits(
    place_id: str,
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[dict]:
    """Return visit history for a place, newest-first.

    Returns 404 if the place does not exist.
    """
    db = request.app.state.db
    place_row = db.execute(
        "SELECT place_id FROM places WHERE place_id=?", (place_id,)
    ).fetchone()
    if place_row is None:
        raise HTTPException(status_code=404, detail="Place not found")
    rows = db.execute(
        "SELECT log_id, place_id, visited_at FROM place_visit_log"
        " WHERE place_id=? ORDER BY visited_at DESC LIMIT ?",
        (place_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/{place_id}/slot-history")
def get_slot_history(
    place_id: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict]:
    """Return the assignment audit trail for all slots of a place, newest-first.

    Each entry: {log_id, slot_id, action, item_id, instance_id, occurred_at}.
    Returns 404 if the place does not exist.
    """
    db = request.app.state.db
    place_row = db.execute(
        "SELECT place_id FROM places WHERE place_id=?", (place_id,)
    ).fetchone()
    if place_row is None:
        raise HTTPException(status_code=404, detail="Place not found")
    rows = db.execute(
        """
        SELECT log_id, slot_id, action, item_id, instance_id, occurred_at
        FROM slot_assignment_log
        WHERE place_id=?
        ORDER BY occurred_at DESC
        LIMIT ?
        """,
        (place_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


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
