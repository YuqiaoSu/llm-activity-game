"""Seed data for challenge_events — limited-window XP multiplier windows.

Dates are relative to the current UTC day so the sample events are always
plausible when a new game.db is created.  The seed is idempotent
(INSERT OR IGNORE).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def get_seed_events() -> list[tuple[str, str, str, float, str, str]]:
    """Return rows as (event_id, label, category, multiplier, starts_at, ends_at)."""
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    return [
        # Currently active — started yesterday, ends tomorrow
        (
            "event_focus_weekend",
            "Focus Weekend",
            "WORK",
            2.0,
            _iso(now - timedelta(days=1)),
            _iso(now + timedelta(days=2)),
        ),
        # Future — starts in 3 days
        (
            "event_social_sprint",
            "Social Sprint",
            "SOCIAL",
            1.5,
            _iso(now + timedelta(days=3)),
            _iso(now + timedelta(days=5)),
        ),
        # Expired — ended 2 days ago
        (
            "event_game_marathon",
            "Game Marathon",
            "GAME",
            1.75,
            _iso(now - timedelta(days=7)),
            _iso(now - timedelta(days=2)),
        ),
    ]
