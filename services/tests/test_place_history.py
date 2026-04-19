"""Tests for GET /places/{id}/history (place activity log)."""
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient

from services.storage.db import init_db


_PLAYER = "player_default"


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    visual = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                         "skin": None, "accessories": [], "anim_state": "idle"})
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES (?, 'T', ?)",
        (_PLAYER, visual),
    )
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")
    conn.execute("INSERT OR IGNORE INTO streak_state (player_id) VALUES ('default')")
    conn.execute(
        "INSERT INTO places (place_id, name, place_type, description, state, item_pool, xp, level)"
        " VALUES ('lab', 'Lab', 'STUDY', 'desc', 'UNLOCKED', '[]', 0, 1)"
    )
    conn.execute(
        "INSERT INTO places (place_id, name, place_type, description, state, item_pool, xp, level)"
        " VALUES ('vault', 'Vault', 'STUDY', 'desc', 'LOCKED', '[]', 0, 1)"
    )
    conn.execute(
        "INSERT INTO player_category_xp (character_id, category, xp) VALUES (?, 'WORK', 1000)",
        (_PLAYER,),
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    from services.api.main import create_app
    return TestClient(create_app(db=db))


# ── history endpoint structure ─────────────────────────────────────────────────

def test_history_returns_empty_list(client):
    r = client.get("/places/lab/history")
    assert r.status_code == 200
    assert r.json() == []


def test_history_404_on_unknown_place(client):
    r = client.get("/places/no_such_place/history")
    assert r.status_code == 404


def test_history_entry_shape(client):
    client.post("/places/lab/invest", json={"xp": 10})
    r = client.get("/places/lab/history")
    entries = r.json()
    assert len(entries) == 1
    entry = entries[0]
    assert "action" in entry
    assert "amount" in entry
    assert "happened_at" in entry


# ── invest logs ────────────────────────────────────────────────────────────────

def test_invest_appears_in_history(client):
    client.post("/places/lab/invest", json={"xp": 50})
    r = client.get("/places/lab/history")
    entries = r.json()
    assert any(e["action"] == "invest" and e["amount"] == 50 for e in entries)


def test_multiple_invests_ordered_newest_first(client):
    client.post("/places/lab/invest", json={"xp": 10})
    client.post("/places/lab/invest", json={"xp": 20})
    client.post("/places/lab/invest", json={"xp": 30})
    r = client.get("/places/lab/history")
    entries = r.json()
    assert entries[0]["amount"] == 30
    assert entries[-1]["amount"] == 10


def test_limit_parameter_respected(client):
    for i in range(5):
        client.post("/places/lab/invest", json={"xp": 10})
    r = client.get("/places/lab/history?limit=3")
    assert len(r.json()) == 3


# ── isolation ──────────────────────────────────────────────────────────────────

def test_history_isolated_per_place(client, db):
    # Insert a log entry directly for another place_id
    import uuid
    from datetime import datetime, timezone
    db.execute(
        "INSERT INTO place_activity_log (log_id, player_id, place_id, action, amount, happened_at)"
        " VALUES (?, ?, 'vault', 'invest', 99, ?)",
        (str(uuid.uuid4()), _PLAYER, datetime.now(timezone.utc).isoformat()),
    )
    db.commit()
    r = client.get("/places/lab/history")
    assert all(e["action"] != "invest" or e["amount"] != 99 for e in r.json())
