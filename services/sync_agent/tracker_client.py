from __future__ import annotations

import random
import time
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

    Retries up to `max_retries` times on connection errors, timeouts, and
    HTTP 503 responses using exponential back-off with ±25 % jitter.
    """

    _RETRYABLE_STATUS = {503, 429}
    _MAX_BACKOFF_SEC = 30.0

    def __init__(
        self,
        base_url: str = "http://localhost:52395",
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay

    def _get_with_retry(self, url: str, params: dict) -> httpx.Response:
        """GET with exponential back-off on transient failures."""
        last_exc: Exception = httpx.HTTPError("max retries exceeded")
        for attempt in range(self.max_retries + 1):
            if attempt > 0:
                base = self.retry_base_delay * (2 ** (attempt - 1))
                delay = min(base, self._MAX_BACKOFF_SEC)
                delay += random.uniform(0, delay * 0.25)
                time.sleep(delay)
            try:
                with httpx.Client(timeout=10.0) as client:
                    response = client.get(url, params=params)
                if response.status_code in self._RETRYABLE_STATUS:
                    last_exc = httpx.HTTPStatusError(
                        f"HTTP {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                    continue
                response.raise_for_status()
                return response
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc = exc
        raise last_exc

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

        response = self._get_with_retry(f"{self.base_url}/api/chunks", params=params)
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

        # Cursor = chunk_end of the newest chunk (raw[-1] after reversal = was raw[0] = newest).
        # Guard: only emit a cursor when chunk_end is a non-empty string so we never
        # save "" and accidentally cause the next poll to re-fetch all chunks.
        new_cursor: str | None = None
        if raw:
            candidate = str(raw[-1].get("chunk_end") or "").strip()
            if candidate:
                new_cursor = candidate
        return result, new_cursor
