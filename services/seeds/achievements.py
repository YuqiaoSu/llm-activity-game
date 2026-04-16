"""Achievement seed definitions.

Each tuple: (achievement_id, name, description, condition_type, threshold)
condition_type values: "total_xp" | "level" | "streak" | "items_collected"
"""
from __future__ import annotations

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
