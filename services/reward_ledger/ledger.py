from __future__ import annotations
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from services.models.item import ItemDefinition

_XP_PER_DROP = 5   # flat XP bonus for receiving any item


def _insert_notification(
    conn: sqlite3.Connection,
    character_id: str,
    event_type: str,
    payload: dict,
) -> None:
    """Insert one row into pending_notifications unless the type is muted.

    Caller is responsible for commit.
    """
    mute_row = conn.execute(
        "SELECT muted FROM notification_prefs WHERE player_id=? AND event_type=?",
        (character_id, event_type),
    ).fetchone()
    if mute_row and mute_row["muted"]:
        return
    conn.execute(
        """
        INSERT INTO pending_notifications (notification_id, character_id, event_type, payload, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            character_id,
            event_type,
            json.dumps(payload),
            datetime.now(timezone.utc).isoformat(),
        ),
    )


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

    # Stamp collection log on first acquisition of this item type
    conn.execute(
        "INSERT OR IGNORE INTO collection_log (player_id, item_id, first_seen_at) VALUES (?, ?, ?)",
        (character_id, item.item_id, now),
    )

    on_wishlist = conn.execute(
        "SELECT 1 FROM wishlist WHERE player_id=? AND item_id=?",
        (character_id, item.item_id),
    ).fetchone() is not None
    _insert_notification(conn, character_id, "item_drop", {
        "item_id": item.item_id,
        "instance_id": instance_id,
        "item_name": item.name,
        "rarity": item.rarity.value,
        "category": item.category.value,
        "wishlisted": on_wishlist,
    })
    conn.commit()
    return True


def insert_streak_milestone_notification(
    conn: sqlite3.Connection,
    character_id: str,
    milestone_days: int,
) -> None:
    """Insert a streak_milestone pending_notification with the milestone day count."""
    _insert_notification(conn, character_id, "streak_milestone", {"milestone": milestone_days})
    conn.commit()


def insert_level_up_notification(
    conn: sqlite3.Connection,
    character_id: str,
    new_level: int,
) -> None:
    """Insert a level_up pending_notification. Caller is responsible for commit."""
    _insert_notification(conn, character_id, "level_up", {"new_level": new_level})


def insert_place_unlock_notification(
    conn: sqlite3.Connection,
    character_id: str,
    place_id: str,
    place_name: str,
    description: str = "",
    condition: str = "",
) -> None:
    """Insert a place_unlock pending_notification. Caller is responsible for commit."""
    _insert_notification(conn, character_id, "place_unlock", {
        "place_id":    place_id,
        "place_name":  place_name,
        "description": description,
        "condition":   condition,
    })


def insert_challenge_notification(
    conn: sqlite3.Connection,
    character_id: str,
    challenge_id: str,
    challenge_name: str,
) -> None:
    """Insert a challenge_complete pending_notification. Caller is responsible for commit."""
    _insert_notification(conn, character_id, "challenge_complete", {
        "challenge_id": challenge_id,
        "name": challenge_name,
    })


def insert_challenge_progress_notification(
    conn: sqlite3.Connection,
    character_id: str,
    challenge_id: str,
    challenge_name: str,
    pct: int,
) -> None:
    """Insert a challenge_progress pending_notification (pct = 50 or 100). Caller commits."""
    _insert_notification(conn, character_id, "challenge_progress", {
        "challenge_id": challenge_id,
        "name": challenge_name,
        "pct": pct,
    })


def insert_xp_milestone_notification(
    conn: sqlite3.Connection,
    character_id: str,
    milestone: int,
    rarity: str,
    item_name: str,
) -> None:
    """Insert an xp_milestone pending_notification. Caller is responsible for commit."""
    _insert_notification(conn, character_id, "xp_milestone", {
        "milestone": milestone,
        "rarity":    rarity,
        "item_name": item_name,
    })


def insert_daily_goal_hit_notification(
    conn: sqlite3.Connection,
    character_id: str,
    target: int,
    xp: int,
    date_str: str,
) -> None:
    """Insert a daily_goal_hit notification. Caller is responsible for commit."""
    _insert_notification(conn, character_id, "daily_goal_hit", {
        "target": target,
        "xp": xp,
        "date": date_str,
    })


def insert_achievement_notification(
    conn: sqlite3.Connection,
    character_id: str,
    achievement_id: str,
    achievement_name: str,
) -> None:
    """Insert an achievement_unlock pending_notification. Caller is responsible for commit."""
    _insert_notification(conn, character_id, "achievement_unlock", {
        "achievement_id": achievement_id,
        "name": achievement_name,
    })


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
