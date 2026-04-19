from __future__ import annotations
import sqlite3
from datetime import datetime, date, timezone

_COOLDOWN_ACTIVE = 60
_COOLDOWN_DORMANT = 10
_DORMANCY_THRESHOLD_DAYS = 3


def adaptive_cooldown(db: sqlite3.Connection) -> int:
    """Return the appropriate poll cooldown in seconds.

    Dormant players (last_active_date > 3 days ago, or never active) get a shorter
    cooldown to ease re-engagement.
    """
    row = db.execute(
        "SELECT last_active_date FROM streak_state WHERE player_id='default'"
    ).fetchone()
    if row is None or row["last_active_date"] is None:
        return _COOLDOWN_DORMANT
    try:
        last = date.fromisoformat(str(row["last_active_date"])[:10])
    except ValueError:
        return _COOLDOWN_DORMANT
    gap = (date.today() - last).days
    return _COOLDOWN_DORMANT if gap > _DORMANCY_THRESHOLD_DAYS else _COOLDOWN_ACTIVE


class RateLimiter:
    def __init__(self, cooldown_sec: int = 60) -> None:
        self.cooldown_sec = cooldown_sec
        self._last_trigger: dict[str, datetime] = {}

    def can_trigger(self, player_id: str) -> bool:
        last = self._last_trigger.get(player_id)
        if last is None:
            return True
        elapsed = (datetime.now(timezone.utc) - last).total_seconds()
        return elapsed >= self.cooldown_sec

    def record_trigger(self, player_id: str) -> None:
        self._last_trigger[player_id] = datetime.now(timezone.utc)
