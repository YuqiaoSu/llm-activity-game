from __future__ import annotations

from datetime import datetime

import httpx


def _hour_to_time_of_day(hour: int) -> str:
    """Map a local hour (0-23) to a human-readable period."""
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 21:
        return "evening"
    return "night"


class TrackerClient:
    """HTTP client for llm-activity-tracker /api/chunks.

    Translates the tracker's response format to the game's Chunk model fields:
      tracker "id"          → chunk_id
      tracker "chunk_start" → started_at
      tracker "interval_min" × 60 → duration_sec
      tracker "label"       → label
      tracker "confidence"  → confidence
      chunk_start hour      → time_of_day

    Cursor is a chunk_end ISO timestamp. Pass None on first poll.
    """

    def __init__(self, base_url: str = "http://localhost:52395") -> None:
        self.base_url = base_url.rstrip("/")

    def fetch_chunks(
        self,
        after_cursor: str | None,
        limit: int = 50,
    ) -> tuple[list[dict], str | None]:
        """GET /api/chunks?started_after=<cursor>&limit=<n>.

        Returns (chunk_dicts, new_cursor).
        Chunks are returned oldest-first for chronological processing.
        new_cursor is the chunk_end of the newest returned chunk.
        """
        params: dict[str, object] = {"limit": limit}
        if after_cursor:
            params["started_after"] = after_cursor

        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{self.base_url}/api/chunks", params=params)
            response.raise_for_status()
            raw: list[dict] = response.json()

        if not isinstance(raw, list):
            return [], None

        # Tracker returns newest-first; reverse for chronological processing.
        raw = list(reversed(raw))

        result: list[dict] = []
        for c in raw:
            chunk_start = str(c.get("chunk_start") or "")
            interval_min = int(c.get("interval_min") or 5)
            try:
                hour = datetime.fromisoformat(chunk_start).astimezone().hour
            except (ValueError, TypeError):
                hour = 12
            result.append({
                "chunk_id": str(c.get("id") or ""),
                "label": str(c.get("label") or ""),
                "duration_sec": interval_min * 60,
                "confidence": float(c.get("confidence") or 0.0),
                "started_at": chunk_start,
                "time_of_day": _hour_to_time_of_day(hour),
            })

        # Cursor = chunk_end of the newest chunk (last item before reversal = index 0 after reversal... wait)
        # raw is reversed, so raw[-1] is the newest chunk (highest chunk_start)
        new_cursor = str(raw[-1].get("chunk_end") or "") if raw else None
        return result, new_cursor
