from __future__ import annotations
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from services.models.item import ItemDefinition
from services.progression.xp import award_category_xp

_XP_PER_DROP = 5   # flat XP bonus for receiving any item


def record_drop(
    conn: sqlite3.Connection,
    chunk_id: str,
    roll_n: int,
    item: ItemDefinition,
    character_id: str,
) -> bool:
    """
    Idempotent drop record. Returns True if newly inserted, False if duplicate.
    On new insert: writes inventory row, awards category XP, queues notification.
    """
    ledger_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    try:
        conn.execute(
            """
            INSERT INTO reward_ledger (ledger_id, chunk_id, roll_n, item_id, character_id, awarded_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (ledger_id, chunk_id, roll_n, item.item_id, character_id, now),
        )
    except sqlite3.IntegrityError:
        conn.rollback()
        return False  # duplicate — silently ignore

    instance_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk)
        VALUES (?, ?, ?, ?, ?)
        """,
        (instance_id, character_id, item.item_id, now, chunk_id),
    )

    # Award XP for the item's category
    award_category_xp(conn, character_id=character_id, category=item.category, xp=_XP_PER_DROP)

    # Queue a notification for Godot
    notification_id = str(uuid.uuid4())
    payload = json.dumps({
        "item_id": item.item_id,
        "instance_id": instance_id,
        "rarity": item.rarity.value,
    })
    conn.execute(
        """
        INSERT INTO pending_notifications (notification_id, character_id, event_type, payload, created_at)
        VALUES (?, ?, 'item_drop', ?, ?)
        """,
        (notification_id, character_id, payload, now),
    )
    conn.commit()
    return True


def get_pending_notifications(
    conn: sqlite3.Connection,
    character_id: str,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM pending_notifications
        WHERE character_id=? AND acknowledged=0
        ORDER BY created_at ASC
        """,
        (character_id,),
    ).fetchall()
