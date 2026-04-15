"""Tests for TrackerClient — field mapping, cursor logic, and retry behaviour."""
from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import httpx
import pytest

from services.sync_agent.tracker_client import TrackerClient, _hour_to_time_of_day


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(data: object, status_code: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = data
    resp.request = MagicMock()
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# _hour_to_time_of_day
# ---------------------------------------------------------------------------

def test_hour_to_time_of_day_morning():
    assert _hour_to_time_of_day(9) == "morning"

def test_hour_to_time_of_day_afternoon():
    assert _hour_to_time_of_day(14) == "afternoon"

def test_hour_to_time_of_day_evening():
    assert _hour_to_time_of_day(19) == "evening"

def test_hour_to_time_of_day_night():
    assert _hour_to_time_of_day(2) == "night"


# ---------------------------------------------------------------------------
# fetch_chunks — field mapping
# ---------------------------------------------------------------------------

RAW_CHUNK = {
    "id": "abc123",
    "chunk_start": "2026-04-14T09:00:00+00:00",
    "chunk_end": "2026-04-14T09:05:00+00:00",
    "interval_min": 5,
    "label": "WORK",
    "confidence": 0.8,
}


def test_fetch_chunks_maps_fields():
    client = TrackerClient(max_retries=0)
    with patch.object(client, "_get_with_retry", return_value=_make_response([RAW_CHUNK])):
        chunks, cursor = client.fetch_chunks(after_cursor=None)

    assert len(chunks) == 1
    c = chunks[0]
    assert c["chunk_id"] == "abc123"
    assert c["label"] == "WORK"
    assert c["duration_sec"] == 300        # 5 min × 60
    assert c["confidence"] == 0.8
    assert c["time_of_day"] == "morning"   # 09:00 UTC → morning


def test_fetch_chunks_cursor_from_chunk_end():
    client = TrackerClient(max_retries=0)
    with patch.object(client, "_get_with_retry", return_value=_make_response([RAW_CHUNK])):
        _, cursor = client.fetch_chunks(after_cursor=None)
    assert cursor == "2026-04-14T09:05:00+00:00"


def test_fetch_chunks_null_chunk_end_returns_no_cursor():
    chunk = {**RAW_CHUNK, "chunk_end": None}
    client = TrackerClient(max_retries=0)
    with patch.object(client, "_get_with_retry", return_value=_make_response([chunk])):
        _, cursor = client.fetch_chunks(after_cursor=None)
    assert cursor is None


def test_fetch_chunks_non_list_response_returns_empty():
    client = TrackerClient(max_retries=0)
    with patch.object(client, "_get_with_retry", return_value=_make_response({"error": "bad"})):
        chunks, cursor = client.fetch_chunks(after_cursor=None)
    assert chunks == []
    assert cursor is None


def test_fetch_chunks_empty_list():
    client = TrackerClient(max_retries=0)
    with patch.object(client, "_get_with_retry", return_value=_make_response([])):
        chunks, cursor = client.fetch_chunks(after_cursor=None)
    assert chunks == []
    assert cursor is None


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------

def test_retry_succeeds_after_transport_error():
    """First HTTP call raises ConnectError; second succeeds — retry loop recovers."""
    client = TrackerClient(max_retries=2, retry_base_delay=0.0)
    good_response = _make_response([RAW_CHUNK])

    call_num = [0]
    def fake_get(url, params=None):
        call_num[0] += 1
        if call_num[0] == 1:
            raise httpx.ConnectError("refused")
        return good_response

    with patch("services.sync_agent.tracker_client.time.sleep"), \
         patch("httpx.Client") as mock_httpx_client:
        mock_ctx = MagicMock()
        mock_httpx_client.return_value.__enter__ = lambda s: mock_ctx
        mock_httpx_client.return_value.__exit__ = MagicMock(return_value=False)
        mock_ctx.get.side_effect = fake_get

        chunks, _ = client.fetch_chunks(after_cursor=None)

    assert len(chunks) == 1
    assert call_num[0] == 2


def test_retry_exhausted_raises():
    """All attempts fail → raises the last exception."""
    client = TrackerClient(max_retries=2, retry_base_delay=0.0)

    with patch("services.sync_agent.tracker_client.time.sleep"):
        with patch.object(
            client, "_get_with_retry",
            side_effect=httpx.ConnectError("refused"),
        ):
            with pytest.raises(httpx.ConnectError):
                client.fetch_chunks(after_cursor=None)


def test_get_with_retry_sleeps_between_attempts():
    """Back-off sleep is called between retries (not before the first attempt)."""
    client = TrackerClient(max_retries=2, retry_base_delay=1.0)
    good_response = _make_response([])

    responses = [httpx.ConnectError("refused"), good_response]

    with patch("services.sync_agent.tracker_client.time.sleep") as mock_sleep, \
         patch("httpx.Client") as mock_httpx_client:
        mock_ctx = MagicMock()
        mock_httpx_client.return_value.__enter__ = lambda s: mock_ctx
        mock_httpx_client.return_value.__exit__ = MagicMock(return_value=False)

        call_num = [0]
        def fake_get(url, params=None):
            r = responses[call_num[0]]
            call_num[0] += 1
            if isinstance(r, Exception):
                raise r
            return r
        mock_ctx.get.side_effect = fake_get

        client.fetch_chunks(after_cursor=None)

    assert mock_sleep.call_count == 1   # slept once, between attempt 0 and 1


def test_get_with_retry_retries_on_503():
    """HTTP 503 is treated as retryable; eventually raises on exhaustion."""
    client = TrackerClient(max_retries=1, retry_base_delay=0.0)

    resp_503 = _make_response([], status_code=503)

    with patch("services.sync_agent.tracker_client.time.sleep"), \
         patch("httpx.Client") as mock_httpx_client:
        mock_ctx = MagicMock()
        mock_httpx_client.return_value.__enter__ = lambda s: mock_ctx
        mock_httpx_client.return_value.__exit__ = MagicMock(return_value=False)
        mock_ctx.get.return_value = resp_503

        with pytest.raises(httpx.HTTPStatusError):
            client.fetch_chunks(after_cursor=None)
