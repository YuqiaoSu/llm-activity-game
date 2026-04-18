"""Companion mood derivation.

Mood is a categorical summary of the player's current engagement state.
It is computed purely from streak and dormancy data — no extra DB queries.

Mood values (ordered worst → best):
  anxious  — dormant for 14+ days
  sad      — dormant (3–13 days inactive)
  neutral  — active but no long streak yet (streak < 7)
  happy    — active with a 7+ day streak
"""
from __future__ import annotations

_ANXIOUS_THRESHOLD_DAYS = 14

_MOOD_XP_MULTIPLIERS: dict[str, float] = {
    "happy":   1.1,
    "neutral": 1.0,
    "sad":     0.9,
    "anxious": 0.8,
}


def mood_xp_multiplier(mood: str) -> float:
    """Return the XP multiplier applied to place XP based on companion mood.

    happy=1.1, neutral=1.0, sad=0.9, anxious=0.8
    """
    return _MOOD_XP_MULTIPLIERS.get(mood, 1.0)


def compute_mood(streak: int, is_dormant: bool, dormant_days: int) -> str:
    """Return one of: 'happy', 'neutral', 'sad', 'anxious'.

    Args:
        streak: current activity streak in days (0 = no streak or first day)
        is_dormant: True when last_active_date > DORMANCY_THRESHOLD_DAYS ago
        dormant_days: days since last activity (0 when active)
    """
    if is_dormant:
        if dormant_days >= _ANXIOUS_THRESHOLD_DAYS:
            return "anxious"
        return "sad"
    if streak >= 7:
        return "happy"
    return "neutral"
