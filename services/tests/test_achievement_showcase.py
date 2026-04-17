"""Tests for achievement pin/unpin showcase endpoints."""
import json
import sqlite3
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.seeds.achievements import SEED_ACHIEVEMENTS
from services.storage.db import init_db


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    for ach in SEED_ACHIEVEMENTS:
        conn.execute(
            "INSERT OR IGNORE INTO achievements "
            "(achievement_id, name, description, condition_type, threshold) VALUES (?, ?, ?, ?, ?)",
            ach,
        )
    visual = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                         "skin": None, "accessories": [], "anim_state": "idle"})
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES (?, ?, ?)",
        ("player_default", "Tester", visual),
    )
    conn.commit()
    yield conn
    conn.close()


def _unlock(db, achievement_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT OR IGNORE INTO player_achievements (player_id, achievement_id, unlocked_at) "
        "VALUES ('player_default', ?, ?)",
        (achievement_id, now),
    )
    db.commit()


@pytest.fixture
def client(db):
    app = create_app(db=db)
    return TestClient(app), db


# ── GET /achievements includes pinned field ──────────────────────────────────

def test_get_achievements_includes_pinned_field(client):
    tc, _ = client
    r = tc.get("/achievements")
    assert r.status_code == 200
    item = r.json()[0]
    assert "pinned" in item
    assert item["pinned"] is False


def test_get_achievements_reflects_pinned_true(client):
    tc, db = client
    ach_id = SEED_ACHIEVEMENTS[0][0]
    _unlock(db, ach_id)
    tc.post(f"/achievements/{ach_id}/pin")

    r = tc.get("/achievements")
    by_id = {a["achievement_id"]: a for a in r.json()}
    assert by_id[ach_id]["pinned"] is True


# ── GET /achievements/pinned ─────────────────────────────────────────────────

def test_get_pinned_empty_when_none_pinned(client):
    tc, _ = client
    r = tc.get("/achievements/pinned")
    assert r.status_code == 200
    assert r.json() == []


def test_get_pinned_returns_pinned_in_order(client):
    tc, db = client
    ids = [a[0] for a in SEED_ACHIEVEMENTS[:2]]
    for ach_id in ids:
        _unlock(db, ach_id)
        tc.post(f"/achievements/{ach_id}/pin")

    r = tc.get("/achievements/pinned")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert data[0]["pin_order"] == 1
    assert data[1]["pin_order"] == 2
    assert data[0]["achievement_id"] == ids[0]


def test_get_pinned_entry_shape(client):
    tc, db = client
    ach_id = SEED_ACHIEVEMENTS[0][0]
    _unlock(db, ach_id)
    tc.post(f"/achievements/{ach_id}/pin")

    r = tc.get("/achievements/pinned")
    entry = r.json()[0]
    for key in ("achievement_id", "name", "description", "condition_type",
                "threshold", "unlocked", "unlocked_at", "pin_order", "pinned_at"):
        assert key in entry


# ── POST /achievements/{id}/pin ──────────────────────────────────────────────

def test_pin_locked_achievement_returns_404(client):
    tc, _ = client
    ach_id = SEED_ACHIEVEMENTS[0][0]
    r = tc.post(f"/achievements/{ach_id}/pin")
    assert r.status_code == 404


def test_pin_nonexistent_achievement_returns_404(client):
    tc, _ = client
    r = tc.post("/achievements/does_not_exist/pin")
    assert r.status_code == 404


def test_pin_already_pinned_returns_409(client):
    tc, db = client
    ach_id = SEED_ACHIEVEMENTS[0][0]
    _unlock(db, ach_id)
    tc.post(f"/achievements/{ach_id}/pin")
    r = tc.post(f"/achievements/{ach_id}/pin")
    assert r.status_code == 409


def test_pin_when_all_slots_full_returns_400(client):
    tc, db = client
    ids = [a[0] for a in SEED_ACHIEVEMENTS[:4]]
    for ach_id in ids:
        _unlock(db, ach_id)
    for ach_id in ids[:3]:
        tc.post(f"/achievements/{ach_id}/pin")
    r = tc.post(f"/achievements/{ids[3]}/pin")
    assert r.status_code == 400


def test_pin_success_response_shape(client):
    tc, db = client
    ach_id = SEED_ACHIEVEMENTS[0][0]
    _unlock(db, ach_id)
    r = tc.post(f"/achievements/{ach_id}/pin")
    assert r.status_code == 200
    data = r.json()
    assert data["achievement_id"] == ach_id
    assert data["pin_order"] == 1
    assert "pinned_at" in data


# ── DELETE /achievements/{id}/pin ────────────────────────────────────────────

def test_unpin_not_pinned_returns_404(client):
    tc, db = client
    ach_id = SEED_ACHIEVEMENTS[0][0]
    _unlock(db, ach_id)
    r = tc.delete(f"/achievements/{ach_id}/pin")
    assert r.status_code == 404


def test_unpin_success_response(client):
    tc, db = client
    ach_id = SEED_ACHIEVEMENTS[0][0]
    _unlock(db, ach_id)
    tc.post(f"/achievements/{ach_id}/pin")
    r = tc.delete(f"/achievements/{ach_id}/pin")
    assert r.status_code == 200
    assert r.json()["unpinned"] is True


def test_unpin_reorders_gap_free(client):
    tc, db = client
    ids = [a[0] for a in SEED_ACHIEVEMENTS[:3]]
    for ach_id in ids:
        _unlock(db, ach_id)
        tc.post(f"/achievements/{ach_id}/pin")

    # Remove the middle pin (order 2)
    tc.delete(f"/achievements/{ids[1]}/pin")

    r = tc.get("/achievements/pinned")
    data = r.json()
    assert len(data) == 2
    orders = {e["achievement_id"]: e["pin_order"] for e in data}
    assert orders[ids[0]] == 1
    assert orders[ids[2]] == 2


def test_unpin_allows_repinning(client):
    tc, db = client
    ids = [a[0] for a in SEED_ACHIEVEMENTS[:4]]
    for ach_id in ids:
        _unlock(db, ach_id)
    for ach_id in ids[:3]:
        tc.post(f"/achievements/{ach_id}/pin")
    tc.delete(f"/achievements/{ids[0]}/pin")
    r = tc.post(f"/achievements/{ids[3]}/pin")
    assert r.status_code == 200
