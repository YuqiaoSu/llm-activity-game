"""XP milestone rewards — guaranteed item drops at fixed total-XP thresholds."""
from __future__ import annotations
import json
import random
import sqlite3

from services.reward_ledger.ledger import insert_xp_milestone_notification

# (threshold_xp, guaranteed_rarity)
XP_MILESTONES: list[tuple[int, str]] = [
    (500,    "RARE"),
    (1000,   "RARE"),
    (2500,   "RARE"),
    (5000,   "EPIC"),
    (10000,  "EPIC"),
]


def _pick_item(conn: sqlite3.Connection, rarity: str) -> dict | None:
    """Return a random item definition at the requested rarity, or any rarity if none found."""
    rows = conn.execute("SELECT item_id, data FROM item_definitions").fetchall()
    at_rarity = [r for r in rows if json.loads(r["data"]).get("rarity") == rarity]
    pool = at_rarity if at_rarity else rows
    if not pool:
        return None
    row = random.choice(pool)
    return json.loads(row["data"])


def check_xp_milestones(
    conn: sqlite3.Connection,
    character_id: str,
    old_total: int,
    new_total: int,
) -> None:
    """Fire milestone rewards for each threshold crossed between old_total and new_total.

    Idempotent: skips thresholds that already have an xp_milestone notification.
    Also awards a guaranteed item via the reward_ledger using a synthetic chunk_id.
    """
    for milestone, rarity in XP_MILESTONES:
        if old_total >= milestone or new_total < milestone:
            continue

        # Check if already notified
        already = conn.execute(
            "SELECT 1 FROM pending_notifications"
            " WHERE character_id=? AND event_type='xp_milestone'"
            " AND json_extract(payload, '$.milestone') = ?",
            (character_id, milestone),
        ).fetchone()
        if already:
            continue

        # Award a guaranteed item
        item_data = _pick_item(conn, rarity)
        item_name = item_data["name"] if item_data else "Mystery Item"
        item_id   = item_data["item_id"] if item_data else None

        if item_id:
            _award_milestone_item(conn, character_id, milestone, item_id)

        insert_xp_milestone_notification(conn, character_id, milestone, rarity, item_name)
        conn.commit()


def _award_milestone_item(
    conn: sqlite3.Connection,
    character_id: str,
    milestone: int,
    item_id: str,
) -> None:
    """Insert into reward_ledger and inventory using a synthetic chunk_id for idempotency."""
    import uuid
    from datetime import datetime, timezone

    synthetic_chunk_id = f"xp_milestone_{milestone}"
    now = datetime.now(timezone.utc).isoformat()

    # Idempotent insert into reward_ledger
    try:
        conn.execute(
            "INSERT INTO reward_ledger (ledger_id, chunk_id, roll_n, item_id, character_id, awarded_at)"
            " VALUES (?, ?, 0, ?, ?, ?)",
            (str(uuid.uuid4()), synthetic_chunk_id, item_id, character_id, now),
        )
    except Exception:
        return  # already awarded (UNIQUE violation)

    # Insert into inventory
    conn.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk)"
        " VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), character_id, item_id, now, synthetic_chunk_id),
    )
