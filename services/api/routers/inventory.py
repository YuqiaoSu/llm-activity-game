import json
import random
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel, field_validator
from services.drop_engine.lottery import DEFAULT_RARITY_WEIGHTS
from services.models.enums import Category

router = APIRouter()

# Ordered rarity tiers — fusion consumes 3× tier N to produce 1× tier N+1
_RARITY_ORDER = ["COMMON", "UNCOMMON", "RARE", "EPIC", "LEGENDARY"]
_FUSE_COUNT = 3   # copies required to fuse

# XP awarded when selling an item by rarity
_SELL_VALUES: dict[str, int] = {
    "COMMON":    5,
    "UNCOMMON": 15,
    "RARE":     30,
    "EPIC":     60,
    "LEGENDARY": 100,
}


class EquipRequest(BaseModel):
    equipped: bool


class FuseRequest(BaseModel):
    item_id: str   # the item type to fuse (must have >= 3 unplaced copies)


class NoteRequest(BaseModel):
    note: str

    from pydantic import field_validator

    @field_validator("note")
    @classmethod
    def validate_note(cls, v: str) -> str:
        if len(v) > 50:
            raise ValueError("note must be 50 characters or fewer")
        return v


@router.get("")
def get_inventory(
    request: Request,
    tag: str | None = Query(default=None, description="Filter items that have this tag on any instance"),
) -> list[dict]:
    """Return inventory grouped by item_id with a quantity count.

    Each entry represents one distinct item type owned by the player.
    Expired items (expires_at < now) are excluded from counts and hidden
    once all instances have expired.  expires_at in the response is the
    earliest non-NULL expiry across all non-expired instances, or NULL
    for permanent items.

    When `tag` is provided only item types are returned where at least one
    instance carries that tag (case-insensitive, exact match within the array).
    """
    db = request.app.state.db
    rows = db.execute(
        """
        SELECT
            i.item_id,
            i.character_id,
            COUNT(CASE WHEN i.expires_at IS NULL OR i.expires_at > datetime('now') THEN 1 END)
                                                   AS quantity,
            MAX(i.acquired_at)                     AS last_acquired_at,
            MAX(CASE WHEN i.equipped THEN 1 ELSE 0 END) AS equipped,
            MIN(CASE WHEN i.placed_in IS NULL
                          AND (i.expires_at IS NULL OR i.expires_at > datetime('now'))
                     THEN i.instance_id END)       AS available_instance_id,
            MIN(CASE WHEN i.expires_at IS NOT NULL
                          AND i.expires_at > datetime('now')
                     THEN i.expires_at END)        AS expires_at,
            MAX(i.note)                            AS note,
            MAX(i.favorite)                        AS favorite,
            COALESCE(MAX(i.tags), '[]')            AS tags,
            MIN(i.durability)                      AS durability,
            MAX(i.locked)                          AS locked,
            json_extract(d.data, '$.name')         AS name,
            json_extract(d.data, '$.rarity')       AS rarity,
            json_extract(d.data, '$.category')     AS category,
            json_extract(d.data, '$.icon')         AS icon,
            json_extract(d.data, '$.description')  AS description,
            json_extract(d.data, '$.effects')      AS effects_json,
            c.first_seen_at,
            CAST(julianday('now') - julianday(MIN(i.acquired_at)) AS INTEGER) AS age_days
        FROM inventory i
        LEFT JOIN item_definitions d ON i.item_id = d.item_id
        LEFT JOIN collection_log c
            ON i.item_id = c.item_id AND c.player_id = 'player_default'
        WHERE i.character_id = 'player_default'
        GROUP BY i.item_id, i.character_id
        HAVING quantity > 0
        ORDER BY last_acquired_at DESC
        """
    ).fetchall()
    import json as _json
    tag_lower = tag.strip().lower() if tag else None
    result = []
    for row in rows:
        d = dict(row)
        raw_effects = d.pop("effects_json", None)
        d["effects"] = _json.loads(raw_effects) if raw_effects else []
        d["description"] = d.get("description") or ""
        raw_tags = d.get("tags", "[]")
        d["tags"] = _json.loads(raw_tags) if isinstance(raw_tags, str) else []
        age_days: int = d.get("age_days") or 0
        d["age_days"] = age_days
        d["is_vintage"] = age_days >= 30
        if tag_lower and not any(t.lower() == tag_lower for t in d["tags"]):
            continue
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
    _assert_not_locked(db, instance_id)

    db.execute("DELETE FROM inventory WHERE instance_id=?", (instance_id,))
    db.commit()
    return {"deleted": True, "instance_id": instance_id}


def _get_sell_value(db, instance_id: str) -> tuple[str, int] | None:
    """Return (rarity, xp_value) for an instance, or None if not found."""
    row = db.execute(
        """
        SELECT json_extract(d.data, '$.rarity') AS rarity
        FROM inventory i
        LEFT JOIN item_definitions d ON i.item_id = d.item_id
        WHERE i.instance_id=? AND i.character_id='player_default'
        """,
        (instance_id,),
    ).fetchone()
    if row is None:
        return None
    rarity: str = row["rarity"] or "COMMON"
    return rarity, _SELL_VALUES.get(rarity, _SELL_VALUES["COMMON"])


@router.get("/instances/{instance_id}/sell-value")
def get_sell_value(instance_id: str, request: Request) -> dict:
    """Return the XP sell value for an inventory instance.

    Returns 404 if the instance doesn't exist or belongs to another player.
    """
    db = request.app.state.db
    result = _get_sell_value(db, instance_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Item instance not found")
    rarity, xp_value = result
    return {"instance_id": instance_id, "rarity": rarity, "xp_value": xp_value}


@router.post("/instances/{instance_id}/sell")
def sell_item(instance_id: str, request: Request) -> dict:
    """Sell an inventory instance for XP based on its rarity.

    Returns 404 if the instance doesn't exist or belongs to another player.
    Returns 409 if the instance is currently placed in a slot.
    """
    from services.progression.xp import award_category_xp
    from services.models.enums import Category

    db = request.app.state.db
    row = db.execute(
        "SELECT instance_id, item_id, placed_in, acquired_at FROM inventory"
        " WHERE instance_id=? AND character_id='player_default'",
        (instance_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Item instance not found")
    if row["placed_in"] is not None:
        raise HTTPException(status_code=409, detail="Item is placed in a slot; remove it first")
    _assert_not_locked(db, instance_id)

    result = _get_sell_value(db, instance_id)
    rarity, base_xp = result if result else ("COMMON", _SELL_VALUES["COMMON"])

    # Vintage bonus: +20% sell value for items held 30+ days
    age_row = db.execute(
        "SELECT CAST(julianday('now') - julianday(acquired_at) AS INTEGER) AS age_days"
        " FROM inventory WHERE instance_id=?",
        (instance_id,),
    ).fetchone()
    age_days: int = int(age_row["age_days"]) if age_row and age_row["age_days"] is not None else 0
    is_vintage = age_days >= 30
    xp_value = int(base_xp * 1.2) if is_vintage else base_xp

    db.execute("DELETE FROM inventory WHERE instance_id=?", (instance_id,))
    award_category_xp(db, "player_default", Category.SPECIAL, xp_value)

    from services.reward_ledger.ledger import _insert_notification
    _insert_notification(db, "player_default", "item_sold", {
        "instance_id": instance_id,
        "item_id":     row["item_id"],
        "rarity":      rarity,
        "xp_awarded":  xp_value,
        "is_vintage":  is_vintage,
    })
    db.commit()
    return {"sold": True, "instance_id": instance_id, "rarity": rarity, "xp_awarded": xp_value, "is_vintage": is_vintage}


class FavoriteRequest(BaseModel):
    favorite: bool


@router.patch("/instances/{instance_id}/favorite")
def patch_inventory_favorite(instance_id: str, body: FavoriteRequest, request: Request) -> dict:
    """Toggle the favorite flag on a specific inventory instance.

    Returns 404 if the instance doesn't exist or belongs to another player.
    """
    db = request.app.state.db
    row = db.execute(
        "SELECT instance_id FROM inventory WHERE instance_id=? AND character_id='player_default'",
        (instance_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Item instance not found")

    db.execute(
        "UPDATE inventory SET favorite=? WHERE instance_id=?",
        (1 if body.favorite else 0, instance_id),
    )
    db.commit()
    return {"instance_id": instance_id, "favorite": body.favorite}


@router.patch("/instances/{instance_id}/note")
def patch_inventory_note(instance_id: str, body: NoteRequest, request: Request) -> dict:
    """Set a freeform note (max 50 chars) on a specific inventory instance.

    Returns 404 if the instance doesn't exist or belongs to another player.
    Pass an empty string to clear the note.
    """
    db = request.app.state.db
    row = db.execute(
        "SELECT instance_id FROM inventory WHERE instance_id=? AND character_id='player_default'",
        (instance_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Item instance not found")

    db.execute(
        "UPDATE inventory SET note=? WHERE instance_id=?",
        (body.note if body.note else None, instance_id),
    )
    db.commit()
    return {"instance_id": instance_id, "note": body.note}


def _assert_not_locked(db, instance_id: str) -> None:
    """Raise 409 if the given inventory instance is locked."""
    row = db.execute(
        "SELECT locked FROM inventory WHERE instance_id=? AND character_id='player_default'",
        (instance_id,),
    ).fetchone()
    if row is not None and int(row["locked"]) == 1:
        raise HTTPException(status_code=409, detail="Item is locked; unlock it before this action")


class LockRequest(BaseModel):
    locked: bool


@router.patch("/instances/{instance_id}/lock")
def patch_inventory_lock(instance_id: str, body: LockRequest, request: Request) -> dict:
    """Toggle the locked flag on a specific inventory instance.

    Returns 404 if the instance doesn't exist or belongs to another player.
    """
    db = request.app.state.db
    row = db.execute(
        "SELECT instance_id FROM inventory WHERE instance_id=? AND character_id='player_default'",
        (instance_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Item instance not found")

    db.execute(
        "UPDATE inventory SET locked=? WHERE instance_id=?",
        (1 if body.locked else 0, instance_id),
    )
    db.commit()
    return {"instance_id": instance_id, "locked": body.locked}


_MAX_TAGS = 3
_MAX_TAG_LEN = 12


class TagsRequest(BaseModel):
    tags: list[str]

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        if len(v) > _MAX_TAGS:
            raise ValueError(f"A maximum of {_MAX_TAGS} tags are allowed")
        cleaned = []
        for tag in v:
            tag = tag.strip()
            if len(tag) > _MAX_TAG_LEN:
                raise ValueError(f"Each tag must be {_MAX_TAG_LEN} characters or fewer (got: {tag!r})")
            if tag:
                cleaned.append(tag)
        return cleaned


@router.patch("/instances/{instance_id}/tags")
def patch_inventory_tags(instance_id: str, body: TagsRequest, request: Request) -> dict:
    """Set the tags list on a specific inventory instance.

    Rules: max 3 tags, each tag ≤12 characters (stripped). Empty strings are ignored.
    Returns 404 if the instance doesn't exist or belongs to another player.
    """
    db = request.app.state.db
    row = db.execute(
        "SELECT instance_id FROM inventory WHERE instance_id=? AND character_id='player_default'",
        (instance_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Item instance not found")

    db.execute(
        "UPDATE inventory SET tags=? WHERE instance_id=?",
        (json.dumps(body.tags), instance_id),
    )
    db.commit()
    return {"instance_id": instance_id, "tags": body.tags}


class BulkSellRequest(BaseModel):
    rarity: str
    category: str | None = None


@router.post("/bulk-sell")
def bulk_sell_items(body: BulkSellRequest, request: Request) -> dict:
    """Sell all unplaced, non-expired instances of a given rarity (and optional category).

    Returns 400 if rarity is not valid.
    Returns {sold_count, total_xp_earned, rarity, category}.
    """
    from services.progression.xp import award_category_xp
    from services.models.enums import Category as XPCategory
    from services.reward_ledger.ledger import _insert_notification

    rarity_upper = body.rarity.upper()
    if rarity_upper not in _RARITY_ORDER:
        raise HTTPException(status_code=400, detail=f"Unknown rarity: {body.rarity!r}")

    xp_per_item = _SELL_VALUES.get(rarity_upper, _SELL_VALUES["COMMON"])
    db = request.app.state.db

    query = """
        SELECT i.instance_id
        FROM inventory i
        JOIN item_definitions d ON i.item_id = d.item_id
        WHERE i.character_id = 'player_default'
          AND i.placed_in IS NULL
          AND i.locked = 0
          AND (i.expires_at IS NULL OR i.expires_at > datetime('now'))
          AND json_extract(d.data, '$.rarity') = ?
    """
    params: list = [rarity_upper]
    if body.category:
        query += " AND json_extract(d.data, '$.category') = ?"
        params.append(body.category.upper())

    rows = db.execute(query, params).fetchall()
    instance_ids = [r["instance_id"] for r in rows]

    if not instance_ids:
        return {"sold_count": 0, "total_xp_earned": 0, "rarity": rarity_upper, "category": body.category}

    total_xp = xp_per_item * len(instance_ids)
    for iid in instance_ids:
        db.execute("DELETE FROM inventory WHERE instance_id=?", (iid,))
    award_category_xp(db, "player_default", XPCategory.SPECIAL, total_xp)
    _insert_notification(db, "player_default", "bulk_item_sold", {
        "rarity":          rarity_upper,
        "category":        body.category,
        "sold_count":      len(instance_ids),
        "total_xp_earned": total_xp,
    })
    db.commit()

    return {
        "sold_count":      len(instance_ids),
        "total_xp_earned": total_xp,
        "rarity":          rarity_upper,
        "category":        body.category,
    }


_REPAIR_COSTS: dict[str, int] = {
    "COMMON":    10,
    "UNCOMMON":  20,
    "RARE":      40,
    "EPIC":      70,
    "LEGENDARY": 100,
}
_DURABILITY_WEAR = 10   # points lost per use-event (slot-assign, donate)
_DURABILITY_MAX  = 100


class BulkRepairRequest(BaseModel):
    rarity: str | None = None


@router.post("/bulk-repair")
def bulk_repair_items(body: BulkRepairRequest, request: Request) -> dict:
    """Repair all worn (durability < 100), unlocked instances in one action.

    Optional `rarity` filter (e.g. "COMMON") restricts which items are repaired.
    Deducts the combined XP cost from the player's total XP.
    Returns 400 on unknown rarity; 402 if insufficient XP.
    Skips locked instances; returns skipped_locked count.
    """
    from services.progression.xp import get_total_xp, deduct_total_xp

    rarity_filter: str | None = None
    if body.rarity is not None:
        rarity_filter = body.rarity.upper()
        if rarity_filter not in _RARITY_ORDER:
            raise HTTPException(status_code=400, detail=f"Unknown rarity: {body.rarity!r}")

    db = request.app.state.db

    # Find all worn unlocked instances
    query = """
        SELECT i.instance_id, i.durability, i.locked,
               json_extract(d.data, '$.rarity') AS rarity
        FROM inventory i
        LEFT JOIN item_definitions d ON i.item_id = d.item_id
        WHERE i.character_id = 'player_default'
          AND i.durability < 100
    """
    params: list = []
    if rarity_filter:
        query += " AND json_extract(d.data, '$.rarity') = ?"
        params.append(rarity_filter)

    rows = db.execute(query, params).fetchall()
    to_repair = [r for r in rows if int(r["locked"]) == 0]
    skipped_locked = len(rows) - len(to_repair)

    if not to_repair:
        return {"repaired_count": 0, "total_xp_spent": 0, "skipped_locked": skipped_locked}

    total_cost = sum(_REPAIR_COSTS.get(r["rarity"] or "COMMON", _REPAIR_COSTS["COMMON"])
                     for r in to_repair)
    total_xp = get_total_xp(db, "player_default")
    if total_xp < total_cost:
        raise HTTPException(
            status_code=402,
            detail=f"Insufficient XP: need {total_cost}, have {total_xp}",
        )

    deduct_total_xp(db, "player_default", total_cost)
    for r in to_repair:
        db.execute(
            "UPDATE inventory SET durability=? WHERE instance_id=?",
            (_DURABILITY_MAX, r["instance_id"]),
        )
    db.commit()

    return {
        "repaired_count": len(to_repair),
        "total_xp_spent": total_cost,
        "skipped_locked": skipped_locked,
    }


@router.post("/instances/{instance_id}/repair")
def repair_item(instance_id: str, request: Request) -> dict:
    """Restore an item instance to full durability (100) for an XP cost.

    Cost is rarity-tiered: COMMON=10, UNCOMMON=20, RARE=40, EPIC=70, LEGENDARY=100 XP.
    Returns 404 if the instance doesn't exist or belongs to another player.
    Returns 409 if the item is already at full durability.
    Returns 402 if the player doesn't have enough XP.
    """
    from services.progression.xp import get_total_xp, deduct_total_xp

    db = request.app.state.db
    row = db.execute(
        """
        SELECT i.instance_id, i.durability,
               json_extract(d.data, '$.rarity') AS rarity
        FROM inventory i
        LEFT JOIN item_definitions d ON i.item_id = d.item_id
        WHERE i.instance_id=? AND i.character_id='player_default'
        """,
        (instance_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Item instance not found")

    current_durability: int = int(row["durability"]) if row["durability"] is not None else _DURABILITY_MAX
    if current_durability >= _DURABILITY_MAX:
        raise HTTPException(status_code=409, detail="Item is already at full durability")

    rarity: str = row["rarity"] or "COMMON"
    cost: int = _REPAIR_COSTS.get(rarity, _REPAIR_COSTS["COMMON"])
    total_xp = get_total_xp(db, "player_default")
    if total_xp < cost:
        raise HTTPException(status_code=402, detail=f"Insufficient XP: need {cost}, have {total_xp}")

    deduct_total_xp(db, "player_default", cost)
    db.execute(
        "UPDATE inventory SET durability=? WHERE instance_id=?",
        (_DURABILITY_MAX, instance_id),
    )
    db.commit()
    return {
        "instance_id": instance_id,
        "durability":  _DURABILITY_MAX,
        "rarity":      rarity,
        "xp_spent":    cost,
    }


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


# Number of COMMON items needed to craft one of each rarity (chain: 2 per step)
_COMMONS_NEEDED: dict[str, int] = {
    "COMMON":    1,
    "UNCOMMON":  2,   # 2 COMMON → 1 UNCOMMON
    "RARE":      4,   # 2 UNCOMMON → 1 RARE  (each needs 2 COMMON)
    "EPIC":      8,
    "LEGENDARY": 16,
}


@router.get("/upgrade-cost")
def get_upgrade_cost(
    request: Request,
    target_rarity: str = Query(...),
    category: str = Query(...),
) -> dict:
    """Return how many COMMON-tier items are needed to craft one of target_rarity."""
    target = target_rarity.upper()
    cat    = category.upper()
    if target not in _COMMONS_NEEDED:
        raise HTTPException(status_code=422, detail=f"Unknown rarity: {target_rarity}")
    if target == "COMMON":
        return {
            "target_rarity": target,
            "category":      cat,
            "items_needed":  0,
            "items_owned":   0,
            "shortfall":     0,
            "xp_equivalent": 0,
        }

    db = request.app.state.db
    needed = _COMMONS_NEEDED[target]

    # Count unplaced, non-expired COMMON items the player owns in this category
    owned_rows = db.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM inventory i
        LEFT JOIN item_definitions d ON i.item_id = d.item_id
        WHERE i.character_id = 'player_default'
          AND (i.expires_at IS NULL OR i.expires_at > datetime('now'))
          AND NOT EXISTS (
              SELECT 1 FROM place_slots ps WHERE ps.occupant_id = i.instance_id
          )
          AND json_extract(d.data, '$.rarity')    = 'COMMON'
          AND json_extract(d.data, '$.category')  = ?
        """,
        (cat,),
    ).fetchone()
    owned: int = owned_rows["cnt"] if owned_rows else 0
    shortfall  = max(0, needed - owned)
    xp_equiv   = shortfall * _SELL_VALUES.get("COMMON", 5)

    return {
        "target_rarity": target,
        "category":      cat,
        "items_needed":  needed,
        "items_owned":   owned,
        "shortfall":     shortfall,
        "xp_equivalent": xp_equiv,
    }


@router.get("/value-summary")
def get_value_summary(request: Request) -> dict:
    """Return aggregate value metrics for the player's inventory."""
    db = request.app.state.db
    rows = db.execute(
        """
        SELECT json_extract(d.data, '$.rarity') AS rarity
        FROM inventory i
        LEFT JOIN item_definitions d ON i.item_id = d.item_id
        WHERE i.character_id = 'player_default'
        """,
    ).fetchall()

    by_rarity: dict[str, int] = {}
    estimated_value = 0
    for row in rows:
        rarity: str = (row["rarity"] or "COMMON").upper()
        by_rarity[rarity] = by_rarity.get(rarity, 0) + 1
        estimated_value += _SELL_VALUES.get(rarity, _SELL_VALUES["COMMON"])

    return {
        "total_items":      len(rows),
        "by_rarity":        by_rarity,
        "estimated_value":  estimated_value,
    }


_AGE_BUCKETS: list[tuple[int | None, str]] = [
    # (max_days_exclusive, label)  — None = no upper bound
    (8,    "0-7d"),
    (31,   "8-30d"),
    (91,   "31-90d"),
    (366,  "91-365d"),
    (None, "365d+"),
]


@router.get("/age-histogram")
def get_age_histogram(request: Request) -> list[dict]:
    """Return item counts and estimated value bucketed by acquisition age."""
    db = request.app.state.db
    rows = db.execute(
        """
        SELECT
            CAST(julianday('now') - julianday(i.acquired_at) AS INTEGER) AS age_days,
            json_extract(d.data, '$.rarity') AS rarity
        FROM inventory i
        LEFT JOIN item_definitions d ON i.item_id = d.item_id
        WHERE i.character_id = 'player_default'
        """,
    ).fetchall()

    buckets: dict[str, dict] = {
        label: {"bucket": label, "count": 0, "value_xp": 0}
        for _, label in _AGE_BUCKETS
    }
    for row in rows:
        age: int = row["age_days"] or 0
        rarity: str = (row["rarity"] or "COMMON").upper()
        xp = _SELL_VALUES.get(rarity, _SELL_VALUES["COMMON"])
        for max_d, label in _AGE_BUCKETS:
            if max_d is None or age < max_d:
                buckets[label]["count"] += 1
                buckets[label]["value_xp"] += xp
                break

    return [buckets[label] for _, label in _AGE_BUCKETS]


@router.get("/recipes")
def get_recipes(request: Request) -> list[dict]:
    """Return crafting recipe templates based on current inventory.

    For each (category, from_rarity) combination the player has unplaced items in,
    returns a recipe entry with:
      category        — item category
      from_rarity     — rarity tier the player would spend
      to_rarity       — resulting rarity (next tier), or null for LEGENDARY
      from_qty        — always 2 (craft requires 2 distinct item types)
      have_item_types — distinct item_ids the player owns (unplaced, correct rarity+category)
      can_craft       — True if have_item_types >= 2
      item_ids        — list of available item_ids for this category+rarity (first 2 used for crafting)
    """
    db = request.app.state.db

    rows = db.execute(
        """
        SELECT json_extract(d.data, '$.category') AS category,
               json_extract(d.data, '$.rarity')   AS rarity,
               COUNT(DISTINCT i.item_id)           AS distinct_types,
               GROUP_CONCAT(DISTINCT i.item_id)    AS item_ids_csv
        FROM inventory i
        JOIN item_definitions d ON i.item_id = d.item_id
        WHERE i.character_id = 'player_default'
          AND i.placed_in IS NULL
        GROUP BY category, rarity
        ORDER BY category ASC, rarity ASC
        """
    ).fetchall()

    result: list[dict] = []
    for row in rows:
        cat = row["category"]
        rarity = row["rarity"]
        if rarity not in _RARITY_ORDER:
            continue
        rarity_idx = _RARITY_ORDER.index(rarity)
        to_rarity = _RARITY_ORDER[rarity_idx + 1] if rarity_idx < len(_RARITY_ORDER) - 1 else None
        distinct = int(row["distinct_types"])
        item_ids = (row["item_ids_csv"] or "").split(",") if row["item_ids_csv"] else []
        result.append({
            "category":        cat,
            "from_rarity":     rarity,
            "to_rarity":       to_rarity,
            "from_qty":        2,
            "have_item_types": distinct,
            "can_craft":       distinct >= 2,
            "item_ids":        item_ids,
        })

    return result


@router.get("/drop-odds")
def get_drop_odds(
    request: Request,
    category: str = Query(..., description="Category name e.g. WORK"),
) -> list[dict]:
    """Return drop probability for each item in a given category.

    Probabilities are computed from DEFAULT_RARITY_WEIGHTS and normalised
    to percentages across all items in that category.
    Returns items sorted by probability descending.
    """
    category_upper = category.upper()
    valid_categories = {c.value for c in Category}
    if category_upper not in valid_categories:
        raise HTTPException(status_code=422, detail=f"Unknown category: {category!r}")

    db = request.app.state.db
    rows = db.execute(
        "SELECT item_id, data FROM item_definitions"
        " WHERE json_extract(data, '$.category') = ?",
        (category_upper,),
    ).fetchall()

    items_raw: list[dict] = []
    for row in rows:
        try:
            d = json.loads(row["data"])
        except (json.JSONDecodeError, TypeError):
            continue
        rarity_str = d.get("rarity", "COMMON")
        from services.models.enums import Rarity
        try:
            rarity_enum = Rarity(rarity_str)
        except ValueError:
            rarity_enum = Rarity.COMMON
        weight = DEFAULT_RARITY_WEIGHTS.get(rarity_enum, 1.0)
        items_raw.append({
            "item_id":  row["item_id"],
            "name":     d.get("name", row["item_id"]),
            "rarity":   rarity_str,
            "_weight":  weight,
        })

    if not items_raw:
        return []

    total_weight = sum(i["_weight"] for i in items_raw)
    result: list[dict] = []
    for item in items_raw:
        pct = round(item["_weight"] / total_weight * 100, 2) if total_weight > 0 else 0.0
        result.append({
            "item_id":         item["item_id"],
            "name":            item["name"],
            "rarity":          item["rarity"],
            "weight":          item["_weight"],
            "probability_pct": pct,
        })

    result.sort(key=lambda x: x["probability_pct"], reverse=True)
    return result


@router.get("/sets")
def get_item_sets(request: Request) -> list[dict]:
    """Return all named item sets with per-item owned status.

    A "set" is defined by items sharing the same `set_id` in their JSON data.
    Each set entry: {set_id, items: [{item_id, name, rarity, owned}],
                     owned_count, total_count, complete}
    Items are sorted by rarity within each set.
    """
    db = request.app.state.db

    # Load all item_definitions that have a set_id
    rows = db.execute(
        "SELECT item_id, data FROM item_definitions"
        " WHERE json_extract(data, '$.set_id') IS NOT NULL"
    ).fetchall()

    if not rows:
        return []

    # Determine which item_ids the player currently owns (non-expired)
    owned_rows = db.execute(
        """
        SELECT DISTINCT item_id
        FROM inventory
        WHERE character_id = 'player_default'
          AND (expires_at IS NULL OR expires_at > datetime('now'))
        """
    ).fetchall()
    owned_ids: set[str] = {r["item_id"] for r in owned_rows}

    _RARITY_ORDER = ["COMMON", "UNCOMMON", "RARE", "EPIC", "LEGENDARY"]

    # Group by set_id
    sets: dict[str, list[dict]] = {}
    for row in rows:
        try:
            d = json.loads(row["data"])
        except (json.JSONDecodeError, TypeError):
            continue
        set_id: str = d.get("set_id") or ""
        if not set_id:
            continue
        item_id = row["item_id"]
        if set_id not in sets:
            sets[set_id] = []
        sets[set_id].append({
            "item_id": item_id,
            "name":    d.get("name", item_id),
            "rarity":  d.get("rarity", "COMMON"),
            "owned":   item_id in owned_ids,
        })

    result: list[dict] = []
    for set_id, items in sorted(sets.items()):
        items.sort(key=lambda i: _RARITY_ORDER.index(i["rarity"])
                   if i["rarity"] in _RARITY_ORDER else 99)
        owned_count = sum(1 for i in items if i["owned"])
        result.append({
            "set_id":       set_id,
            "items":        items,
            "owned_count":  owned_count,
            "total_count":  len(items),
            "complete":     owned_count == len(items),
        })

    return result
