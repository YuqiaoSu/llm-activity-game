"""Tests for SyncAgent.poll_with_summary and the /sync/poll-now rich response."""
from __future__ import annotations

import json
import sqlite3
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.storage.db import init_db
from services.sync_agent.agent import SyncAgent, PollResult
from services.sync_agent.tracker_client import TrackerClient
from services.sync_agent.rate_limiter import RateLimiter


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=OFF")
    init_db(conn)
    visual = json.dumps({
        "base_sprite": "x.png", "evolution_stage": 0,
        "skin": None, "accessories": [], "anim_state": "idle",
    })
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES ('player_default', 'T', ?)",
        (visual,),
    )
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")
    conn.execute(
        "INSERT INTO item_definitions (item_id, data) VALUES (?, ?)",
        ("scroll", json.dumps({
            "item_id": "scroll", "name": "Scroll", "rarity": "COMMON",
            "category": "WORK", "icon": "", "effects": [], "description": "",
            "drop_requirement": {},
        })),
    )
    conn.commit()
    yield conn
    conn.close()


def _make_agent(db, chunks, cursor, rate_limiter=None):
    mock_client = MagicMock(spec=TrackerClient)
    mock_client.fetch_chunks.return_value = (chunks, cursor)
    return SyncAgent(
        db=db, tracker_client=mock_client, character_id="player_default",
        rate_limiter=rate_limiter or RateLimiter(cooldown_sec=0),
    )


def _chunk(chunk_id="c1", label="WORK", duration_sec=600):
    return {
        "chunk_id": chunk_id,
        "started_at": "2026-01-01T10:00:00+00:00",
        "duration_sec": duration_sec,
        "label": label,
        "confidence": 0.9,
        "time_of_day": "morning",
    }


def test_poll_with_summary_ok_returns_result_ok(db):
    summary = _make_agent(db, [_chunk()], "c1").poll_with_summary(manual=True)
    assert summary["result"] == "OK"


def test_poll_with_summary_returns_total_xp(db):
    summary = _make_agent(db, [_chunk(duration_sec=600)], "c1").poll_with_summary(manual=True)
    # 600s / 60 = 10 XP/min → 10 XP (base)
    assert summary["total_xp"] >= 1


def test_poll_with_summary_returns_xp_by_category(db):
    summary = _make_agent(db, [_chunk(label="WORK")], "c1").poll_with_summary(manual=True)
    assert "WORK" in summary["xp_by_category"]
    assert summary["xp_by_category"]["WORK"] >= 1


def test_poll_with_summary_returns_chunks_processed(db):
    summary = _make_agent(db, [_chunk("c1"), _chunk("c2")], "c2").poll_with_summary(manual=True)
    assert summary["chunks_processed"] >= 1


def test_poll_with_summary_on_cooldown(db):
    from services.sync_agent.rate_limiter import RateLimiter
    rl = RateLimiter(cooldown_sec=9999)
    rl.record_trigger("player_default")
    summary = _make_agent(db, [], None, rate_limiter=rl).poll_with_summary(manual=True)
    assert summary["result"] == "ON_COOLDOWN"
    assert summary["total_xp"] == 0


def test_poll_with_summary_no_chunks(db):
    summary = _make_agent(db, [], None).poll_with_summary(manual=True)
    assert summary["result"] == "NO_NEW_CHUNKS"


def test_poll_now_endpoint_returns_result_field(db):
    """POST /sync/poll-now response must include 'result' key."""
    mock_client = MagicMock(spec=TrackerClient)
    mock_client.fetch_chunks.return_value = ([_chunk()], "c1")
    app = create_app(db=db)
    app.state.sync_agent = SyncAgent(
        db=db, tracker_client=mock_client, character_id="player_default",
        rate_limiter=RateLimiter(cooldown_sec=0),
    )
    client = TestClient(app)
    resp = client.post("/sync/poll-now")
    assert resp.status_code == 200
    body = resp.json()
    assert "result" in body


def test_poll_now_endpoint_returns_summary_fields_on_ok(db):
    """When OK, /sync/poll-now should return total_xp and xp_by_category."""
    mock_client = MagicMock(spec=TrackerClient)
    mock_client.fetch_chunks.return_value = ([_chunk()], "c1")
    app = create_app(db=db)
    app.state.sync_agent = SyncAgent(
        db=db, tracker_client=mock_client, character_id="player_default",
        rate_limiter=RateLimiter(cooldown_sec=0),
    )
    client = TestClient(app)
    resp = client.post("/sync/poll-now")
    assert resp.status_code == 200
    body = resp.json()
    assert body["result"] == "OK"
    assert "total_xp" in body
    assert "xp_by_category" in body
    assert "drops_earned" in body
