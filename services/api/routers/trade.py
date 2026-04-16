"""NPC trade post API.

GET  /trade/offers          — list all offers with player's current affordability
POST /trade/accept          — execute a trade (consume from_qty items, grant to_qty items)
"""
from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()

_CHARACTER_ID = "player_default"


def _get_offers_with_availability(db) -> list[dict]:
    """Return all trade offers annotated with have_enough (bool) and have_qty (int)."""
    offers = db.execute("SELECT * FROM trade_offers ORDER BY offer_id").fetchall()
    result = []
    for o in offers:
        offer = dict(o)
        # Count unplaced instances of from_rarity (and from_category if set)
        if offer["from_category"]:
            row = db.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM inventory i
                JOIN item_definitions d ON i.item_id = d.item_id
                WHERE i.character_id = ?
                  AND i.placed_in IS NULL
                  AND json_extract(d.data, '$.rarity') = ?
                  AND json_extract(d.data, '$.category') = ?
                """,
                (_CHARACTER_ID, offer["from_rarity"], offer["from_category"]),
            ).fetchone()
        else:
            row = db.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM inventory i
                JOIN item_definitions d ON i.item_id = d.item_id
                WHERE i.character_id = ?
                  AND i.placed_in IS NULL
                  AND json_extract(d.data, '$.rarity') = ?
                """,
                (_CHARACTER_ID, offer["from_rarity"]),
            ).fetchone()
        have_qty = int(row["cnt"])
        offer["have_qty"] = have_qty
        offer["have_enough"] = have_qty >= offer["from_qty"]
        result.append(offer)
    return result


@router.get("/offers")
def get_trade_offers(request: Request) -> list[dict]:
    db = request.app.state.db
    return _get_offers_with_availability(db)


class AcceptTradeBody(BaseModel):
    offer_id: str


@router.post("/accept")
def accept_trade(body: AcceptTradeBody, request: Request) -> dict:
    """Execute a trade offer.

    Consumes from_qty unplaced instances of from_rarity (filtered by from_category
    if set) and grants to_qty new instances of a random item of to_rarity
    (filtered by to_category if set).

    Raises 404 if offer not found, 400 if player cannot afford it or no target
    item exists.
    """
    db = request.app.state.db

    offer_row = db.execute(
        "SELECT * FROM trade_offers WHERE offer_id = ?", (body.offer_id,)
    ).fetchone()
    if offer_row is None:
        raise HTTPException(status_code=404, detail="Trade offer not found")

    offer = dict(offer_row)

    # Fetch eligible source instances (unplaced, correct rarity, optional category)
    if offer["from_category"]:
        source_rows = db.execute(
            """
            SELECT i.instance_id
            FROM inventory i
            JOIN item_definitions d ON i.item_id = d.item_id
            WHERE i.character_id = ?
              AND i.placed_in IS NULL
              AND json_extract(d.data, '$.rarity') = ?
              AND json_extract(d.data, '$.category') = ?
            ORDER BY i.acquired_at ASC
            LIMIT ?
            """,
            (_CHARACTER_ID, offer["from_rarity"], offer["from_category"], offer["from_qty"]),
        ).fetchall()
    else:
        source_rows = db.execute(
            """
            SELECT i.instance_id
            FROM inventory i
            JOIN item_definitions d ON i.item_id = d.item_id
            WHERE i.character_id = ?
              AND i.placed_in IS NULL
              AND json_extract(d.data, '$.rarity') = ?
            ORDER BY i.acquired_at ASC
            LIMIT ?
            """,
            (_CHARACTER_ID, offer["from_rarity"], offer["from_qty"]),
        ).fetchall()

    if len(source_rows) < offer["from_qty"]:
        raise HTTPException(
            status_code=400,
            detail=f"Not enough items: need {offer['from_qty']} × {offer['from_rarity']}, "
                   f"have {len(source_rows)}",
        )

    # Find candidate output items
    if offer["to_category"]:
        candidates = db.execute(
            """
            SELECT item_id FROM item_definitions
            WHERE json_extract(data, '$.rarity') = ?
              AND json_extract(data, '$.category') = ?
            """,
            (offer["to_rarity"], offer["to_category"]),
        ).fetchall()
    else:
        candidates = db.execute(
            "SELECT item_id FROM item_definitions WHERE json_extract(data, '$.rarity') = ?",
            (offer["to_rarity"],),
        ).fetchall()

    if not candidates:
        raise HTTPException(
            status_code=400,
            detail=f"No items of rarity {offer['to_rarity']} exist in the catalogue",
        )

    # Consume source items
    for row in source_rows:
        db.execute("DELETE FROM inventory WHERE instance_id = ?", (row["instance_id"],))

    # Grant output items
    now = datetime.now(timezone.utc).isoformat()
    granted = []
    for _ in range(offer["to_qty"]):
        target_item_id: str = random.choice(candidates)["item_id"]
        new_instance_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk) "
            "VALUES (?, ?, ?, ?, 'trade')",
            (new_instance_id, _CHARACTER_ID, target_item_id, now),
        )
        granted.append({"instance_id": new_instance_id, "item_id": target_item_id})

    db.commit()

    return {
        "offer_id":  offer["offer_id"],
        "consumed":  [r["instance_id"] for r in source_rows],
        "granted":   granted,
        "traded_at": now,
    }
