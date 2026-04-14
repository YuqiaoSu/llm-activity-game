from __future__ import annotations
from datetime import datetime, timezone


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
