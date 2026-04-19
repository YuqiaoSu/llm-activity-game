"""Code-driven achievement milestones — no DB seeding required.

Unlike DB-seeded achievements, these milestones are defined in code so they
work on a fresh database. Each milestone auto-inserts its definition into the
achievements table (idempotent via INSERT OR IGNORE) so they appear in
GET /achievements.
"""
from __future__ import annotations
import sqlite3
from datetime import datetime, timezone
from services.progression.xp import get_total_xp, compute_level
from services.progression.streak import get_streak
from services.reward_ledger.ledger import insert_achievement_notification


# (achievement_id, name, description, condition_type, threshold)
_MILESTONES: list[tuple[str, str, str, str, int]] = [
    (
        "first_drop",
        "First Drop",
        "Receive your first item drop.",
        "items_collected", 1,
    ),
    (
        "level_5_milestone",
        "Level 5 Reached",
        "Reach Level 5 on your journey.",
        "level", 5,
    ),
    (
        "streak_warrior",
        "Streak Warrior",
        "Maintain a 14-day activity streak.",
        "streak", 14,
    ),
    (
        "xp_1000",
        "XP Milestone: 1,000",
        "Accumulate 1,000 total XP.",
        "total_xp", 1000,
    ),
    (
        "xp_10000",
        "XP Milestone: 10,000",
        "Accumulate 10,000 total XP.",
        "total_xp", 10000,
    ),
]


def _get_stats(db: sqlite3.Connection, character_id: str) -> dict[str, int]:
    total_xp = get_total_xp(db, character_id)
    level = compute_level(total_xp)
    streak = get_streak(db)
    items_row = db.execute(
        "SELECT COUNT(DISTINCT item_id) AS n FROM inventory WHERE character_id=?",
        (character_id,),
    ).fetchone()
    return {
        "total_xp":        total_xp,
        "level":           level,
        "streak":          streak["current_streak"],
        "items_collected": int(items_row["n"]) if items_row else 0,
    }


def check_and_unlock_milestones(
    db: sqlite3.Connection,
    character_id: str = "player_default",
) -> list[str]:
    """Unlock milestones whose criteria are newly met.

    Ensures milestone definitions exist in the achievements table (idempotent),
    then checks each one against current player stats.
    Returns a list of newly-unlocked achievement_ids. Caller must commit.
    """
    for aid, name, description, condition_type, threshold in _MILESTONES:
        db.execute(
            "INSERT OR IGNORE INTO achievements"
            " (achievement_id, name, description, condition_type, threshold)"
            " VALUES (?, ?, ?, ?, ?)",
            (aid, name, description, condition_type, threshold),
        )

    already_unlocked = {
        row["achievement_id"]
        for row in db.execute(
            "SELECT achievement_id FROM player_achievements WHERE player_id=?",
            (character_id,),
        ).fetchall()
    }

    stats = _get_stats(db, character_id)
    now = datetime.now(timezone.utc).isoformat()
    newly_unlocked: list[str] = []

    # Reverse map for chain_next lookup
    child_rows = db.execute(
        "SELECT achievement_id, name, parent_achievement_id FROM achievements"
        " WHERE parent_achievement_id IS NOT NULL"
    ).fetchall()
    child_map: dict[str, str] = {r["parent_achievement_id"]: r["name"] for r in child_rows}

    for aid, name, desc, condition_type, threshold in _MILESTONES:
        if aid in already_unlocked:
            continue
        if stats.get(condition_type, 0) >= threshold:
            db.execute(
                "INSERT OR IGNORE INTO player_achievements"
                " (player_id, achievement_id, unlocked_at) VALUES (?, ?, ?)",
                (character_id, aid, now),
            )
            insert_achievement_notification(
                db, character_id, aid, name,
                description=desc,
                chain_next=child_map.get(aid),
            )
            newly_unlocked.append(aid)

    return newly_unlocked
