"""Tests for GET /achievements/export-text."""
import json
import sqlite3
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

from services.storage.db import init_db

_PLAYER = "player_default"
_VISUAL = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                      "skin": None, "accessories": [], "anim_state": "idle"})


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES (?, 'Hero', ?)",
        (_PLAYER, _VISUAL),
    )
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")
    conn.execute("INSERT OR IGNORE INTO streak_state (player_id) VALUES ('default')")
    conn.execute(
        "INSERT INTO achievements (achievement_id, name, description, condition_type, threshold)"
        " VALUES ('ach_a', 'First Drop', 'Get your first item', 'item_drop', 1)"
    )
    conn.execute(
        "INSERT INTO achievements (achievement_id, name, description, condition_type, threshold)"
        " VALUES ('ach_b', 'Level Up', 'Reach level 2', 'level_reached', 2)"
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    from services.api.main import create_app
    return TestClient(create_app(db=db))


def _unlock(db, ach_id: str, days_ago: int = 0) -> None:
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    db.execute(
        "INSERT OR IGNORE INTO player_achievements (player_id, achievement_id, unlocked_at)"
        " VALUES ('player_default', ?, ?)",
        (ach_id, ts),
    )
    db.commit()


# ── GET /achievements/export-text ─────────────────────────────────────────────

def test_export_text_shape(client):
    r = client.get("/achievements/export-text")
    assert r.status_code == 200
    d = r.json()
    assert "text" in d
    assert "count" in d


def test_export_text_no_unlocked(client):
    r = client.get("/achievements/export-text")
    assert r.json()["count"] == 0


def test_export_text_count_matches_unlocked(client, db):
    _unlock(db, "ach_a")
    _unlock(db, "ach_b")
    r = client.get("/achievements/export-text")
    assert r.json()["count"] == 2


def test_export_text_contains_name(client, db):
    _unlock(db, "ach_a")
    r = client.get("/achievements/export-text")
    assert "First Drop" in r.json()["text"]
    assert "Get your first item" in r.json()["text"]


def test_export_text_header_line(client, db):
    r = client.get("/achievements/export-text")
    assert "Hero" in r.json()["text"]
    assert "===" in r.json()["text"]


def test_export_text_sorted_by_date(client, db):
    _unlock(db, "ach_a", days_ago=2)
    _unlock(db, "ach_b", days_ago=0)
    text = client.get("/achievements/export-text").json()["text"]
    pos_a = text.find("First Drop")
    pos_b = text.find("Level Up")
    assert pos_a < pos_b  # older unlock appears first
