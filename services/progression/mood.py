"""Companion mood derivation and player-set drop mood.

Mood is a categorical summary of the player's current engagement state.
It is computed purely from streak and dormancy data — no extra DB queries.

Mood values (ordered worst → best):
  anxious  — dormant for 14+ days
  sad      — dormant (3–13 days inactive)
  neutral  — active but no long streak yet (streak < 7)
  happy    — active with a 7+ day streak
"""
from __future__ import annotations
import sqlite3
from datetime import datetime, timezone, timedelta

_ANXIOUS_THRESHOLD_DAYS = 14
_MOOD_DECAY_HOURS = 24
_VALID_PLAYER_MOODS = frozenset({"happy", "neutral", "sad", "anxious"})

_MOOD_XP_MULTIPLIERS: dict[str, float] = {
    "happy":   1.1,
    "neutral": 1.0,
    "sad":     0.9,
    "anxious": 0.8,
}

# Drop rate multipliers for player-set mood (slightly different from place XP multipliers)
_DROP_MOOD_MULTIPLIERS: dict[str, float] = {
    "happy":   1.15,
    "neutral": 1.0,
    "sad":     0.9,
    "anxious": 0.85,
}


def drop_mood_multiplier(db: sqlite3.Connection) -> float:
    """Return drop-rate multiplier based on the player's self-set mood.

    Reads `mood` and `mood_set_at` from player_profile. If mood_set_at is
    older than 24 h, treats the mood as 'neutral' (decay back to baseline).
    """
    row = db.execute(
        "SELECT mood, mood_set_at FROM player_profile WHERE character_id='player_default'"
    ).fetchone()
    if row is None:
        return 1.0
    mood: str = row["mood"] or "neutral"
    mood_set_at: str | None = row["mood_set_at"]
    if mood_set_at:
        try:
            set_at = datetime.fromisoformat(mood_set_at)
            if set_at.tzinfo is None:
                set_at = set_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - set_at > timedelta(hours=_MOOD_DECAY_HOURS):
                mood = "neutral"
        except ValueError:
            mood = "neutral"
    return _DROP_MOOD_MULTIPLIERS.get(mood, 1.0)


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
