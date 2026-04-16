"""Weekly challenge seed definitions.

Each tuple: (challenge_id, name, description, category, metric, threshold)
metric values:
  'xp'         — XP earned in the specified category this week
  'total_xp'   — total XP earned across all categories this week
  'categories' — number of distinct categories in which XP was earned this week
For 'total_xp' and 'categories', category is set to 'ALL' (unused in logic).
"""
from __future__ import annotations

SEED_WEEKLY_CHALLENGES: list[tuple[str, str, str, str, str, int]] = [
    (
        "work_sprint",
        "Work Sprint",
        "Earn 300 WORK XP in a single week.",
        "WORK", "xp", 300,
    ),
    (
        "creative_flow",
        "Creative Flow",
        "Earn 200 CREATIVE XP in a single week.",
        "CREATIVE", "xp", 200,
    ),
    (
        "learning_week",
        "Learning Week",
        "Earn 250 LEARNING XP in a single week.",
        "LEARNING", "xp", 250,
    ),
    (
        "reflection_time",
        "Reflection Time",
        "Earn 150 REFLECTION XP in a single week.",
        "REFLECTION", "xp", 150,
    ),
    (
        "social_butterfly",
        "Social Butterfly",
        "Earn 100 SOCIAL XP in a single week.",
        "SOCIAL", "xp", 100,
    ),
    (
        "variety_pack",
        "Variety Pack",
        "Earn XP in at least 3 different activity categories this week.",
        "ALL", "categories", 3,
    ),
    (
        "big_week",
        "Big Week",
        "Earn 500 total XP across all categories in a single week.",
        "ALL", "total_xp", 500,
    ),
]
