from __future__ import annotations
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from services.models.item import ItemDefinition

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
    Uses a savepoint so duplicate detection never rolls back an outer transaction.
    """
    now = datetime.now(timezone.utc).isoformat()
    ledger_id = str(uuid.uuid4())

    conn.execute("SAVEPOINT record_drop")
    try:
        conn.execute(
            """
            INSERT INTO reward_ledger (ledger_id, chunk_id, roll_n, item_id, character_id, awarded_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (ledger_id, chunk_id, roll_n, item.item_id, character_id, now),
        )
        conn.execute("RELEASE SAVEPOINT record_drop")
    except sqlite3.IntegrityError:
        conn.execute("ROLLBACK TO SAVEPOINT record_drop")
        conn.execute("RELEASE SAVEPOINT record_drop")
        return False

    instance_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk)
        VALUES (?, ?, ?, ?, ?)
        """,
        (instance_id, character_id, item.item_id, now, chunk_id),
    )

    # Inline XP upsert — do NOT call award_category_xp() to avoid premature commit
    conn.execute(
        """
        INSERT INTO player_category_xp (character_id, category, xp)
        VALUES (?, ?, ?)
        ON CONFLICT (character_id, category) DO UPDATE SET xp = xp + excluded.xp
        """,
        (character_id, str(item.category.value), _XP_PER_DROP),
    )

    notification_id = str(uuid.uuid4())
    payload = json.dumps({
        "item_id": item.item_id,
        "instance_id": instance_id,
        "item_name": item.name,
        "rarity": item.rarity.value,
        "category": item.category.value,
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


def insert_level_up_notification(
    conn: sqlite3.Connection,
    character_id: str,
    new_level: int,
) -> None:
    """Insert a LEVEL_UP pending_notification. Caller is responsible for commit."""
    notification_id = str(uuid.uuid4())
    payload = json.dumps({"new_level": new_level})
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO pending_notifications (notification_id, character_id, event_type, payload, created_at)
        VALUES (?, ?, 'level_up', ?, ?)
        """,
        (notification_id, character_id, payload, now),
    )


def insert_place_unlock_notification(
    conn: sqlite3.Connection,
    character_id: str,
    place_id: str,
    place_name: str,
) -> None:
    """Insert a PLACE_UNLOCK pending_notification. Caller is responsible for commit."""
    notification_id = str(uuid.uuid4())
    payload = json.dumps({"place_id": place_id, "place_name": place_name})
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO pending_notifications (notification_id, character_id, event_type, payload, created_at)
        VALUES (?, ?, 'place_unlock', ?, ?)
        """,
        (notification_id, character_id, payload, now),
    )


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
