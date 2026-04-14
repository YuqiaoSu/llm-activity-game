from __future__ import annotations
import httpx


class TrackerClient:
    """HTTP client for llm-activity-tracker /v1/chunks."""

    def __init__(self, base_url: str = "http://localhost:8000") -> None:
        self.base_url = base_url.rstrip("/")

    def fetch_chunks(
        self,
        after_cursor: str | None,
        limit: int = 50,
    ) -> tuple[list[dict], str | None]:
        """
        GET /v1/chunks?after_cursor=<id>&limit=<n>
        Returns (list_of_chunk_dicts, new_cursor_or_None).
        new_cursor is the last chunk_id in the response, or None if empty.
        """
        params: dict = {"limit": limit}
        if after_cursor:
            params["after_cursor"] = after_cursor

        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{self.base_url}/v1/chunks", params=params)
            response.raise_for_status()
            data = response.json()

        chunks: list[dict] = data if isinstance(data, list) else data.get("chunks", [])
        new_cursor = chunks[-1]["chunk_id"] if chunks else None
        return chunks, new_cursor
