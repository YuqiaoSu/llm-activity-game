"""Tests for item vintage bonus (30+ day held items sell for 20% more XP)."""
import json
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

from services.storage.db import init_db

_PLAYER = "player_default"
_VISUAL = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                      "skin": None, "accessories": [], "anim_state": "idle"})
_ITEM_DATA = json.dumps({"item_id": "test_sword", "name": "Test Sword",
                          "rarity": "COMMON", "category": "WORK",
                          "description": "", "effects": []})
_RARE_DATA = json.dumps({"item_id": "rare_ring", "name": "Rare Ring",
                          "rarity": "RARE", "category": "WORK",
                          "description": "", "effects": []})


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES (?, 'T', ?)",
        (_PLAYER, _VISUAL),
    )
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")
    conn.execute("INSERT OR IGNORE INTO streak_state (player_id) VALUES ('default')")
    conn.execute("INSERT INTO item_definitions (item_id, data) VALUES ('test_sword', ?)", (_ITEM_DATA,))
    conn.execute("INSERT INTO item_definitions (item_id, data) VALUES ('rare_ring', ?)", (_RARE_DATA,))
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    from services.api.main import create_app
    return TestClient(create_app(db=db))


def _add_instance(db, item_id: str, days_old: int = 0) -> str:
    iid = str(uuid.uuid4())
    acquired = (datetime.now(timezone.utc) - timedelta(days=days_old)).isoformat()
    db.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk)"
        " VALUES (?, ?, ?, ?, 'test_chunk')",
        (iid, _PLAYER, item_id, acquired),
    )
    db.commit()
    return iid


# ── age_days and is_vintage in GET /inventory ─────────────────────────────────

def test_age_days_in_get(client, db):
    _add_instance(db, "test_sword", days_old=0)
    r = client.get("/inventory")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert "age_days" in items[0]
    assert "is_vintage" in items[0]


def test_new_item_not_vintage(client, db):
    _add_instance(db, "test_sword", days_old=0)
    r = client.get("/inventory")
    assert r.json()[0]["is_vintage"] is False


def test_29_day_item_not_vintage(client, db):
    _add_instance(db, "test_sword", days_old=29)
    r = client.get("/inventory")
    assert r.json()[0]["is_vintage"] is False


def test_30_day_item_is_vintage(client, db):
    _add_instance(db, "test_sword", days_old=30)
    r = client.get("/inventory")
    assert r.json()[0]["is_vintage"] is True
    assert r.json()[0]["age_days"] >= 30


def test_old_item_is_vintage(client, db):
    _add_instance(db, "test_sword", days_old=60)
    r = client.get("/inventory")
    assert r.json()[0]["is_vintage"] is True


# ── sell value with vintage multiplier ───────────────────────────────────────

def test_non_vintage_sell_value_normal(client, db):
    iid = _add_instance(db, "test_sword", days_old=0)
    r = client.post(f"/inventory/instances/{iid}/sell")
    assert r.status_code == 200
    assert r.json()["xp_awarded"] == 5   # COMMON base = 5
    assert r.json()["is_vintage"] is False


def test_vintage_sell_value_boosted(client, db):
    iid = _add_instance(db, "test_sword", days_old=30)
    r = client.post(f"/inventory/instances/{iid}/sell")
    assert r.status_code == 200
    assert r.json()["xp_awarded"] == 6   # 5 * 1.2 = 6
    assert r.json()["is_vintage"] is True


def test_vintage_rare_sell_value_boosted(client, db):
    iid = _add_instance(db, "rare_ring", days_old=30)
    r = client.post(f"/inventory/instances/{iid}/sell")
    assert r.status_code == 200
    assert r.json()["xp_awarded"] == 36  # 30 * 1.2 = 36
    assert r.json()["is_vintage"] is True
