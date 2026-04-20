"""Tests for GET /player/mastery and mastery.py tier logic."""
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient

from services.storage.db import init_db
from services.progression.mastery import mastery_entry, tier_for_level, level_from_xp

_VISUAL = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                      "skin": None, "accessories": [], "anim_state": "idle"})


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES ('player_default', 'T', ?)",
        (_VISUAL,),
    )
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")
    conn.execute("INSERT OR IGNORE INTO streak_state (player_id) VALUES ('default')")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    from services.api.main import create_app
    return TestClient(create_app(db=db))


# ── unit tests ──────────────────────────────────────────────────────────────

def test_level_from_xp_zero():
    assert level_from_xp(0) == 1


def test_level_from_xp_boundary():
    assert level_from_xp(49) == 1
    assert level_from_xp(50) == 2
    assert level_from_xp(99) == 2
    assert level_from_xp(100) == 3


def test_tier_for_level_novice():
    tier, emoji = tier_for_level(1)
    assert tier == "Novice"
    assert emoji == "🌱"


def test_tier_for_level_grandmaster():
    tier, emoji = tier_for_level(51)
    assert tier == "Grandmaster"
    assert emoji == "👑"

    tier2, _ = tier_for_level(999)
    assert tier2 == "Grandmaster"


def test_mastery_entry_shape():
    entry = mastery_entry("WORK", 100)
    assert entry["category"] == "WORK"
    assert entry["xp"] == 100
    assert entry["level"] == 3
    assert "tier" in entry
    assert "tier_emoji" in entry
    assert "next_level_xp" in entry


# ── API tests ───────────────────────────────────────────────────────────────

def test_no_category_xp_returns_empty(client):
    r = client.get("/player/mastery")
    assert r.status_code == 200
    assert r.json() == []


def test_mastery_response_shape(client, db):
    db.execute(
        "INSERT INTO player_category_xp (character_id, category, xp) VALUES ('player_default', 'WORK', 50)"
    )
    db.commit()
    r = client.get("/player/mastery")
    assert r.status_code == 200
    entries = r.json()
    assert len(entries) == 1
    e = entries[0]
    assert e["category"] == "WORK"
    assert e["xp"] == 50
    assert e["level"] == 2
    assert "tier" in e
    assert "tier_emoji" in e
    assert "next_level_xp" in e


def test_sorted_by_xp_desc(client, db):
    db.execute("INSERT INTO player_category_xp (character_id, category, xp) VALUES ('player_default', 'WORK', 10)")
    db.execute("INSERT INTO player_category_xp (character_id, category, xp) VALUES ('player_default', 'LEARN', 200)")
    db.commit()
    entries = client.get("/player/mastery").json()
    assert entries[0]["category"] == "LEARN"
    assert entries[1]["category"] == "WORK"


def test_tier_progression(client, db):
    # 250 XP → level 6 → Apprentice
    db.execute("INSERT INTO player_category_xp (character_id, category, xp) VALUES ('player_default', 'WORK', 250)")
    db.commit()
    entry = client.get("/player/mastery").json()[0]
    assert entry["tier"] == "Apprentice"
    assert entry["tier_emoji"] == "📘"
