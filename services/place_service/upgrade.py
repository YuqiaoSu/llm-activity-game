"""Place XP and levelling system.

Each active place (one with at least one slotted item) gains XP equal to the
chunk XP awarded while that item is slotted.  Level thresholds grow quadratically:
  level N requires N² × 50 cumulative XP to reach.

  Level 1:   0 XP  (start)
  Level 2:  50 XP
  Level 3: 200 XP
  Level 4: 450 XP
  Level 5: 800 XP
  ...
  Level N: (N-1)² × 50 XP
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def xp_threshold(level: int) -> int:
    """Minimum cumulative XP to reach `level` (level 1 = 0)."""
    if level <= 1:
        return 0
    return (level - 1) ** 2 * 50


def xp_to_level(xp: int) -> int:
    """Return the level corresponding to `xp` cumulative XP."""
    level = 1
    while xp >= xp_threshold(level + 1):
        level += 1
        if level >= 20:   # cap at 20 to avoid unbounded loop
            break
    return level


def award_place_xp(
    db: sqlite3.Connection,
    place_id: str,
    xp: int,
    character_id: str = "player_default",
) -> bool:
    """Award `xp` to a place and trigger a level-up notification if the level changed.

    Returns True if the place levelled up, False otherwise.
    """
    if xp <= 0:
        return False

    row = db.execute(
        "SELECT xp, level FROM places WHERE place_id=?",
        (place_id,),
    ).fetchone()
    if row is None:
        return False

    old_xp: int   = row["xp"]
    old_level: int = row["level"]
    new_xp: int   = old_xp + xp
    new_level: int = xp_to_level(new_xp)

    db.execute(
        "UPDATE places SET xp=?, level=? WHERE place_id=?",
        (new_xp, new_level, place_id),
    )

    levelled_up = new_level > old_level
    if levelled_up:
        name_row = db.execute(
            "SELECT name FROM places WHERE place_id=?", (place_id,)
        ).fetchone()
        place_name = name_row["name"] if name_row else place_id
        _insert_place_level_notification(db, character_id, place_id, place_name, new_level)

    return levelled_up


def _insert_place_level_notification(
    db: sqlite3.Connection,
    character_id: str,
    place_id: str,
    place_name: str,
    new_level: int,
) -> None:
    import uuid
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        """
        INSERT OR IGNORE INTO pending_notifications
            (notification_id, character_id, event_type, payload, created_at)
        VALUES (?, ?, 'place_level_up', ?, ?)
        """,
        (
            str(uuid.uuid4()),
            character_id,
            f'{{"place_id":"{place_id}","place_name":"{place_name}","new_level":{new_level}}}',
            now,
        ),
    )


def get_active_place_ids(db: sqlite3.Connection) -> list[str]:
    """Return place IDs that currently have at least one occupied slot."""
    rows = db.execute(
        """
        SELECT DISTINCT place_id
        FROM place_slots
        WHERE occupant_id IS NOT NULL
        """
    ).fetchall()
    return [r["place_id"] for r in rows]
