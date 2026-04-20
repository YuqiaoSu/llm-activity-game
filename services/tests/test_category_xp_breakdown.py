"""Tests for category_breakdown in GET /player/profile."""
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient

from services.storage.db import init_db

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


def _set_xp(db, category: str, xp: int) -> None:
    db.execute(
        "INSERT OR REPLACE INTO player_category_xp (character_id, category, xp) VALUES ('player_default', ?, ?)",
        (category, xp),
    )
    db.commit()


def test_category_breakdown_present(client):
    r = client.get("/player/profile")
    assert r.status_code == 200
    assert "category_breakdown" in r.json()


def test_category_breakdown_is_list(client):
    r = client.get("/player/profile")
    assert isinstance(r.json()["category_breakdown"], list)


def test_category_breakdown_sorted_by_xp(client, db):
    _set_xp(db, "WORK", 200)
    _set_xp(db, "LEARN", 50)
    _set_xp(db, "SOCIAL", 150)
    r = client.get("/player/profile")
    breakdown = r.json()["category_breakdown"]
    xps = [e["xp"] for e in breakdown]
    assert xps == sorted(xps, reverse=True)


def test_category_breakdown_level_computed(client, db):
    _set_xp(db, "WORK", 100)   # level = 100//50+1 = 3
    r = client.get("/player/profile")
    breakdown = r.json()["category_breakdown"]
    work_entry = next(e for e in breakdown if e["category"] == "WORK")
    assert work_entry["level"] == 3


def test_category_breakdown_zero_xp_level_one(client, db):
    _set_xp(db, "SOCIAL", 0)
    r = client.get("/player/profile")
    breakdown = r.json()["category_breakdown"]
    social = next((e for e in breakdown if e["category"] == "SOCIAL"), None)
    assert social is not None
    assert social["level"] == 1


def test_category_breakdown_xp_50_level_2(client, db):
    _set_xp(db, "LEARN", 50)
    r = client.get("/player/profile")
    breakdown = r.json()["category_breakdown"]
    learn = next(e for e in breakdown if e["category"] == "LEARN")
    assert learn["level"] == 2


def test_category_breakdown_fields(client, db):
    _set_xp(db, "WORK", 10)
    r = client.get("/player/profile")
    breakdown = r.json()["category_breakdown"]
    assert len(breakdown) > 0
    entry = breakdown[0]
    assert set(entry.keys()) >= {"category", "xp", "level"}
