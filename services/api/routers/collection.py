from __future__ import annotations
from fastapi import APIRouter, Request

router = APIRouter()


@router.get("")
def get_collection(request: Request) -> list[dict]:
    """Return all item definitions annotated with discovery status.

    Each entry is one item type.  `discovered` is True if the player has ever
    received that item; `first_seen_at` is the ISO timestamp of first acquisition
    or null for undiscovered items.

    Undiscovered items still appear in the list (with name / rarity / category
    visible) so the player can see the full catalogue and track progress.
    """
    db = request.app.state.db
    rows = db.execute(
        """
        SELECT
            d.item_id,
            json_extract(d.data, '$.name')        AS name,
            json_extract(d.data, '$.rarity')      AS rarity,
            json_extract(d.data, '$.category')    AS category,
            json_extract(d.data, '$.icon')        AS icon,
            CASE WHEN c.item_id IS NOT NULL THEN 1 ELSE 0 END AS discovered,
            c.first_seen_at
        FROM item_definitions d
        LEFT JOIN collection_log c
            ON c.item_id   = d.item_id
            AND c.player_id = 'player_default'
        ORDER BY discovered DESC, d.item_id
        """,
    ).fetchall()

    return [
        {
            "item_id":       row["item_id"],
            "name":          row["name"],
            "rarity":        row["rarity"],
            "category":      row["category"],
            "icon":          row["icon"],
            "discovered":    bool(row["discovered"]),
            "first_seen_at": row["first_seen_at"],
        }
        for row in rows
    ]
