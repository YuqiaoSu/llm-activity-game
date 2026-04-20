"""Tests for place visit streak milestone rewards."""
import json
import sqlite3
import uuid
import pytest
from datetime import date, timedelta
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
    # Seed at least one item definition so rewards can be awarded
    item_data = json.dumps({
        "name": "Seed Item", "rarity": "COMMON", "category": "WORK",
        "drop_requirement": {}, "icon": "", "description": "",
    })
    conn.execute(
        "INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES ('seed_item', ?)",
        (item_data,),
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    from services.api.main import create_app
    return TestClient(create_app(db=db))


def _make_place(db, place_id: str = "p1") -> str:
    db.execute(
        "INSERT INTO places (place_id, name, place_type, description, category, state,"
        " item_pool, metadata)"
        " VALUES (?, 'Test', 'WORK', '', 'WORK', 'UNLOCKED', '{}', '{}')",
        (place_id,),
    )
    db.commit()
    return place_id


def _set_streak(db, place_id: str, streak: int, days_ago: int = 1) -> None:
    d = (date.today() - timedelta(days=days_ago)).isoformat()
    db.execute(
        "UPDATE places SET visit_streak=?, last_visit_date=? WHERE place_id=?",
        (streak, d, place_id),
    )
    db.commit()


def test_no_reward_at_streak_2(client, db):
    _make_place(db)
    _set_streak(db, "p1", 1)  # yesterday streak=1 → today becomes 2
    r = client.post("/places/p1/visit")
    assert r.status_code == 200
    assert r.json()["streak_days"] == 2
    assert "reward_item_id" not in r.json()


def test_reward_at_streak_3(client, db):
    _make_place(db)
    _set_streak(db, "p1", 2)  # yesterday streak=2 → today becomes 3
    r = client.post("/places/p1/visit")
    assert r.status_code == 200
    assert r.json()["streak_days"] == 3
    assert "reward_item_id" in r.json()


def test_reward_idempotent(client, db):
    _make_place(db)
    _set_streak(db, "p1", 2)
    r1 = client.post("/places/p1/visit")
    assert "reward_item_id" in r1.json()
    # Same day visit keeps streak=3, tries same chunk_id → no double award
    r2 = client.post("/places/p1/visit")
    assert r2.status_code == 200
    assert "reward_item_id" not in r2.json()


def test_reward_item_in_inventory(client, db):
    _make_place(db)
    _set_streak(db, "p1", 2)
    r = client.post("/places/p1/visit")
    reward_id = r.json().get("reward_item_id")
    assert reward_id is not None
    inv = client.get("/inventory").json()
    all_item_ids = [i["item_id"] for i in inv]
    assert reward_id in all_item_ids


def test_notification_inserted(client, db):
    _make_place(db)
    _set_streak(db, "p1", 2)
    client.post("/places/p1/visit")
    row = db.execute(
        "SELECT event_type FROM pending_notifications WHERE event_type='place_streak_reward'"
    ).fetchone()
    assert row is not None


def test_reward_at_streak_7(client, db):
    _make_place(db)
    _set_streak(db, "p1", 6)
    r = client.post("/places/p1/visit")
    assert r.json()["streak_days"] == 7
    assert "reward_item_id" in r.json()


def test_reward_at_streak_14(client, db):
    _make_place(db)
    _set_streak(db, "p1", 13)
    r = client.post("/places/p1/visit")
    assert r.json()["streak_days"] == 14
    assert "reward_item_id" in r.json()
