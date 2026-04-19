"""Achievement seed definitions.

Each tuple: (achievement_id, name, description, condition_type, threshold)
condition_type values: "total_xp" | "level" | "streak" | "items_collected"
"""
from __future__ import annotations
import sqlite3

SEED_ACHIEVEMENTS: list[tuple[str, str, str, str, int]] = [
    (
        "first_blood",
        "First Blood",
        "Earn your first XP from an activity session.",
        "total_xp", 1,
    ),
    (
        "getting_warmed_up",
        "Getting Warmed Up",
        "Accumulate 500 total XP.",
        "total_xp", 500,
    ),
    (
        "dedicated",
        "Dedicated",
        "Accumulate 5,000 total XP.",
        "total_xp", 5000,
    ),
    (
        "veteran",
        "Veteran",
        "Accumulate 25,000 total XP.",
        "total_xp", 25000,
    ),
    # Chain starters for level chain
    (
        "first_level",
        "First Steps",
        "Reach Level 1.",
        "level", 1,
    ),
    (
        "level_5",
        "Rising Star",
        "Reach Level 5.",
        "level", 5,
    ),
    (
        "level_10",
        "Double Digits",
        "Reach Level 10.",
        "level", 10,
    ),
    (
        "on_a_roll",
        "On a Roll",
        "Maintain a 3-day activity streak.",
        "streak", 3,
    ),
    (
        "unstoppable",
        "Unstoppable",
        "Maintain a 7-day activity streak.",
        "streak", 7,
    ),
    # Chain starter for items chain
    (
        "first_item",
        "First Pickup",
        "Collect your first item.",
        "items_collected", 1,
    ),
    (
        "collector",
        "Collector",
        "Collect 10 items.",
        "items_collected", 10,
    ),
    (
        "hoarder",
        "Hoarder",
        "Collect 50 items.",
        "items_collected", 50,
    ),
]

# Chain parent links: child_id → parent_id
# Chain 1 (XP):    first_blood → getting_warmed_up → dedicated
# Chain 2 (level): first_level → level_5 → level_10
# Chain 3 (items): first_item  → collector → hoarder
CHAIN_PARENTS: dict[str, str] = {
    "getting_warmed_up": "first_blood",
    "dedicated":         "getting_warmed_up",
    "level_5":           "first_level",
    "level_10":          "level_5",
    "collector":         "first_item",
    "hoarder":           "collector",
}


def seed_achievements(conn: sqlite3.Connection) -> None:
    """Insert achievement definitions and set chain parent links. Idempotent."""
    for ach_id, name, desc, ctype, threshold in SEED_ACHIEVEMENTS:
        conn.execute(
            "INSERT OR IGNORE INTO achievements"
            " (achievement_id, name, description, condition_type, threshold)"
            " VALUES (?, ?, ?, ?, ?)",
            (ach_id, name, desc, ctype, threshold),
        )
    for child_id, parent_id in CHAIN_PARENTS.items():
        conn.execute(
            "UPDATE achievements SET parent_achievement_id=? WHERE achievement_id=?",
            (parent_id, child_id),
        )
    conn.commit()
