"""Loot table browser — shows all droppable items grouped by category.

GET /catalogue                      — all items, flat list
GET /catalogue/by-category          — dict keyed by category
GET /catalogue/by-category/{cat}    — single category list

Each item entry includes a `discovered` flag from the player's collection_log
so the client can show ??? placeholders for undiscovered items without losing
the count of what's possible.
"""
from __future__ import annotations

import json
from fastapi import APIRouter, Request, HTTPException

router = APIRouter()

_PLAYER_ID = "player_default"


def _load_catalogue(db) -> list[dict]:
    """Return all item_definitions joined with collection discovery and wishlist status."""
    rows = db.execute(
        """
        SELECT
            d.item_id,
            json_extract(d.data, '$.name')        AS name,
            json_extract(d.data, '$.rarity')      AS rarity,
            json_extract(d.data, '$.category')    AS category,
            json_extract(d.data, '$.description') AS description,
            json_extract(d.data, '$.effects')     AS effects_json,
            CASE WHEN c.item_id IS NOT NULL THEN 1 ELSE 0 END AS discovered,
            c.first_seen_at,
            CASE WHEN w.item_id IS NOT NULL THEN 1 ELSE 0 END AS wishlisted
        FROM item_definitions d
        LEFT JOIN collection_log c
            ON d.item_id = c.item_id AND c.player_id = ?
        LEFT JOIN wishlist w
            ON d.item_id = w.item_id AND w.player_id = ?
        ORDER BY d.item_id
        """,
        (_PLAYER_ID, _PLAYER_ID),
    ).fetchall()

    result = []
    for row in rows:
        entry = {
            "item_id":      row["item_id"],
            "name":         row["name"],
            "rarity":       row["rarity"],
            "category":     row["category"],
            "description":  row["description"] or "",
            "effects":      json.loads(row["effects_json"]) if row["effects_json"] else [],
            "discovered":   bool(row["discovered"]),
            "first_seen_at": row["first_seen_at"],
            "wishlisted":   bool(row["wishlisted"]),
        }
        result.append(entry)
    return result


@router.get("")
def get_catalogue(request: Request) -> list[dict]:
    """Return all item definitions with discovery status, sorted by category then rarity."""
    db = request.app.state.db
    items = _load_catalogue(db)
    _RARITY_ORDER = ["COMMON", "UNCOMMON", "RARE", "EPIC", "LEGENDARY"]
    items.sort(key=lambda i: (
        i.get("category") or "",
        _RARITY_ORDER.index(i["rarity"]) if i["rarity"] in _RARITY_ORDER else 99,
        i["item_id"],
    ))
    return items


@router.get("/by-category")
def get_catalogue_by_category(request: Request) -> dict[str, list[dict]]:
    """Return items grouped by category.

    Keys are category strings (e.g. "WORK", "GAME").
    Within each category items are sorted by rarity (common → legendary).
    """
    db = request.app.state.db
    items = _load_catalogue(db)
    _RARITY_ORDER = ["COMMON", "UNCOMMON", "RARE", "EPIC", "LEGENDARY"]

    grouped: dict[str, list[dict]] = {}
    for item in items:
        cat = item.get("category") or "UNKNOWN"
        grouped.setdefault(cat, []).append(item)

    for cat in grouped:
        grouped[cat].sort(key=lambda i: (
            _RARITY_ORDER.index(i["rarity"]) if i["rarity"] in _RARITY_ORDER else 99,
            i["item_id"],
        ))

    return grouped


@router.get("/wishlist")
def get_wishlist(request: Request) -> list[dict]:
    """Return all items the player has wishlisted, sorted by category then rarity."""
    db = request.app.state.db
    items = _load_catalogue(db)
    wishlisted = [i for i in items if i["wishlisted"]]
    _RARITY_ORDER = ["COMMON", "UNCOMMON", "RARE", "EPIC", "LEGENDARY"]
    wishlisted.sort(key=lambda i: (
        i.get("category") or "",
        _RARITY_ORDER.index(i["rarity"]) if i["rarity"] in _RARITY_ORDER else 99,
    ))
    return wishlisted


@router.post("/{item_id}/wishlist")
def add_to_wishlist(item_id: str, request: Request) -> dict:
    """Add an item to the player's wishlist.

    Returns 404 if the item doesn't exist in the catalogue.
    Returns 409 if already wishlisted.
    """
    from datetime import datetime, timezone
    db = request.app.state.db

    exists = db.execute(
        "SELECT 1 FROM item_definitions WHERE item_id=?", (item_id,)
    ).fetchone()
    if exists is None:
        raise HTTPException(status_code=404, detail="Item not found in catalogue")

    already = db.execute(
        "SELECT 1 FROM wishlist WHERE player_id=? AND item_id=?", (_PLAYER_ID, item_id)
    ).fetchone()
    if already:
        raise HTTPException(status_code=409, detail="Item is already wishlisted")

    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO wishlist (player_id, item_id, added_at) VALUES (?, ?, ?)",
        (_PLAYER_ID, item_id, now),
    )
    db.commit()
    return {"item_id": item_id, "wishlisted": True, "added_at": now}


@router.delete("/{item_id}/wishlist")
def remove_from_wishlist(item_id: str, request: Request) -> dict:
    """Remove an item from the player's wishlist.

    Returns 404 if the item is not currently wishlisted.
    """
    db = request.app.state.db

    existing = db.execute(
        "SELECT 1 FROM wishlist WHERE player_id=? AND item_id=?", (_PLAYER_ID, item_id)
    ).fetchone()
    if existing is None:
        raise HTTPException(status_code=404, detail="Item is not wishlisted")

    db.execute(
        "DELETE FROM wishlist WHERE player_id=? AND item_id=?", (_PLAYER_ID, item_id)
    )
    db.commit()
    return {"item_id": item_id, "wishlisted": False}


@router.get("/by-category/{category}")
def get_catalogue_for_category(category: str, request: Request) -> list[dict]:
    """Return items for a single category (case-insensitive).

    Returns 404 if no items exist for that category.
    """
    db = request.app.state.db
    items = _load_catalogue(db)
    cat_upper = category.upper()
    filtered = [i for i in items if (i.get("category") or "").upper() == cat_upper]
    if not filtered:
        raise HTTPException(status_code=404, detail=f"No items found for category: {category}")

    _RARITY_ORDER = ["COMMON", "UNCOMMON", "RARE", "EPIC", "LEGENDARY"]
    filtered.sort(key=lambda i: (
        _RARITY_ORDER.index(i["rarity"]) if i["rarity"] in _RARITY_ORDER else 99,
        i["item_id"],
    ))
    return filtered
