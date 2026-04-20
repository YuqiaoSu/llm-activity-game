"""Category mastery tier computation."""

_TIERS: list[tuple[int, str, str]] = [
    # (min_level, tier_name, emoji)
    (51, "Grandmaster", "👑"),
    (36, "Master",      "⭐"),
    (21, "Expert",      "🔥"),
    (11, "Journeyman",  "⚙️"),
    (6,  "Apprentice",  "📘"),
    (1,  "Novice",      "🌱"),
]


def level_from_xp(xp: int) -> int:
    return xp // 50 + 1


def next_level_xp(level: int) -> int:
    return level * 50


def tier_for_level(level: int) -> tuple[str, str]:
    """Return (tier_name, emoji) for the given level."""
    for min_lv, name, emoji in _TIERS:
        if level >= min_lv:
            return name, emoji
    return "Novice", "🌱"


def mastery_entry(category: str, xp: int) -> dict:
    lv = level_from_xp(xp)
    tier, emoji = tier_for_level(lv)
    return {
        "category":      category,
        "xp":            xp,
        "level":         lv,
        "tier":          tier,
        "tier_emoji":    emoji,
        "next_level_xp": next_level_xp(lv),
    }
