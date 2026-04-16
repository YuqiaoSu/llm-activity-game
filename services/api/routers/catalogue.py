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
    """Return all item_definitions joined with collection discovery status."""
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
            c.first_seen_at
        FROM item_definitions d
        LEFT JOIN collection_log c
            ON d.item_id = c.item_id AND c.player_id = ?
        ORDER BY d.item_id
        """,
        (_PLAYER_ID,),
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
