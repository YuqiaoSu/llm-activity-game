"""Achievement unlock checking.

check_achievements() is called once per poll after the streak is updated.
It reads all conditions in two queries, then loops over definitions in Python
— no per-achievement DB round-trip.
"""
from __future__ import annotations
import sqlite3
from datetime import datetime, timezone
from services.reward_ledger.ledger import insert_achievement_notification


def _current_state(conn: sqlite3.Connection, character_id: str) -> dict:
    """Fetch all metrics needed for condition evaluation in minimal queries."""
    xp_row = conn.execute(
        "SELECT COALESCE(SUM(xp), 0) AS total_xp FROM player_category_xp WHERE character_id=?",
        (character_id,),
    ).fetchone()

    level_row = conn.execute(
        "SELECT level FROM player_profile WHERE character_id=?",
        (character_id,),
    ).fetchone()

    streak_row = conn.execute(
        "SELECT current_streak FROM streak_state WHERE player_id='default'"
    ).fetchone()

    items_row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM inventory WHERE character_id=?",
        (character_id,),
    ).fetchone()

    return {
        "total_xp":        xp_row["total_xp"] if xp_row else 0,
        "level":           level_row["level"] if level_row else 1,
        "streak":          streak_row["current_streak"] if streak_row else 0,
        "items_collected": items_row["cnt"] if items_row else 0,
    }


def check_achievements(conn: sqlite3.Connection, character_id: str) -> list[str]:
    """Unlock any achievements whose conditions are now met.

    Returns a list of newly-unlocked achievement_ids.
    Caller is responsible for commit.
    """
    all_defs = conn.execute(
        "SELECT achievement_id, name, description, condition_type, threshold FROM achievements"
    ).fetchall()

    # Build reverse map: parent_id → child (achievement_id, name) for chain_next lookup
    child_map: dict[str, tuple[str, str]] = {}
    for row in conn.execute(
        "SELECT achievement_id, name, parent_achievement_id FROM achievements"
        " WHERE parent_achievement_id IS NOT NULL"
    ).fetchall():
        child_map[row["parent_achievement_id"]] = (row["achievement_id"], row["name"])

    if not all_defs:
        return []

    already_unlocked = {
        row["achievement_id"]
        for row in conn.execute(
            "SELECT achievement_id FROM player_achievements WHERE player_id=?",
            (character_id,),
        ).fetchall()
    }

    state = _current_state(conn, character_id)
    now = datetime.now(timezone.utc).isoformat()
    newly_unlocked: list[str] = []

    for row in all_defs:
        aid = row["achievement_id"]
        if aid in already_unlocked:
            continue

        met = state.get(row["condition_type"], 0) >= row["threshold"]
        if not met:
            continue

        conn.execute(
            "INSERT INTO player_achievements (player_id, achievement_id, unlocked_at) VALUES (?, ?, ?)",
            (character_id, aid, now),
        )
        child = child_map.get(aid)
        chain_next = child[1] if child else None
        insert_achievement_notification(
            conn, character_id, aid, row["name"],
            description=row["description"] or "",
            chain_next=chain_next,
        )
        newly_unlocked.append(aid)

    return newly_unlocked
