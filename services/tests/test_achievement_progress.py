"""Tests for achievement progress bars — GET /achievements now returns progress + progress_pct."""
import json
import sqlite3
import uuid
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
    conn.execute("INSERT OR IGNORE INTO streak_state (player_id) VALUES ('default')")
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    app = create_app(db=db)
    return TestClient(app), db


def _unlock(db, achievement_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT OR IGNORE INTO player_achievements (player_id, achievement_id, unlocked_at) "
        "VALUES ('player_default', ?, ?)",
        (achievement_id, now),
    )
    db.commit()


def _add_xp(db, xp: int) -> None:
    db.execute(
        "INSERT INTO player_category_xp (character_id, category, xp) VALUES ('player_default', 'WORK', ?)"
        " ON CONFLICT (character_id, category) DO UPDATE SET xp = xp + excluded.xp",
        (xp,),
    )
    db.commit()


def _set_streak(db, days: int) -> None:
    db.execute(
        "INSERT OR REPLACE INTO streak_state (player_id, current_streak) VALUES ('default', ?)",
        (days,),
    )
    db.commit()


def _add_item(db) -> None:
    instance_id = str(uuid.uuid4())
    item_id = "item_" + str(uuid.uuid4())[:8]
    db.execute(
        "INSERT INTO item_definitions (item_id, data) VALUES (?, '{}')",
        (item_id,),
    )
    db.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk) "
        "VALUES (?, 'player_default', ?, datetime('now'), 'chunk_x')",
        (instance_id, item_id),
    )
    db.commit()


# ── response shape ────────────────────────────────────────────────────────────

def test_achievements_response_has_progress_fields(client):
    tc, _ = client
    r = tc.get("/achievements")
    assert r.status_code == 200
    entries = r.json()
    assert len(entries) > 0
    for e in entries:
        assert "progress" in e
        assert "progress_pct" in e


# ── locked achievement progress ───────────────────────────────────────────────

def test_locked_total_xp_progress_reflects_current_xp(client):
    tc, db = client
    _add_xp(db, 450)
    entries = tc.get("/achievements").json()
    xp_entries = [e for e in entries if e["condition_type"] == "total_xp" and not e["unlocked"]]
    assert len(xp_entries) > 0
    # First (lowest threshold) locked xp achievement should show progress >= 450
    first = xp_entries[0]
    assert first["progress"] == min(450, first["threshold"])


def test_locked_streak_progress_reflects_current_streak(client):
    tc, db = client
    _set_streak(db, 4)
    entries = tc.get("/achievements").json()
    streak_entries = [e for e in entries if e["condition_type"] == "streak" and not e["unlocked"]]
    if streak_entries:
        first = streak_entries[0]
        assert first["progress"] == min(4, first["threshold"])


def test_locked_items_progress_reflects_inventory_count(client):
    tc, db = client
    _add_item(db)
    _add_item(db)
    entries = tc.get("/achievements").json()
    item_entries = [e for e in entries if e["condition_type"] == "items_collected" and not e["unlocked"]]
    if item_entries:
        first = item_entries[0]
        assert first["progress"] == min(2, first["threshold"])


# ── progress_pct calculation ──────────────────────────────────────────────────

def test_progress_pct_is_100_when_unlocked(client):
    tc, db = client
    # Unlock the first achievement
    entries = tc.get("/achievements").json()
    first_id = entries[0]["achievement_id"]
    _unlock(db, first_id)
    updated = tc.get("/achievements").json()
    entry = next(e for e in updated if e["achievement_id"] == first_id)
    assert entry["progress_pct"] == 100


def test_progress_pct_zero_when_no_progress(client):
    tc, _ = client
    entries = tc.get("/achievements").json()
    xp_entries = [e for e in entries if e["condition_type"] == "total_xp" and not e["unlocked"]]
    if xp_entries:
        assert xp_entries[0]["progress_pct"] == 0


def test_progress_pct_partial(client):
    tc, db = client
    _add_xp(db, 100)
    entries = tc.get("/achievements").json()
    # Find an achievement whose threshold is > 100 (locked)
    bigger = [e for e in entries
              if e["condition_type"] == "total_xp" and e["threshold"] > 100 and not e["unlocked"]]
    if bigger:
        first = bigger[0]
        expected_pct = min(100, round(100 / first["threshold"] * 100))
        assert first["progress_pct"] == expected_pct


def test_progress_capped_at_threshold(client):
    tc, db = client
    _add_xp(db, 99999)
    entries = tc.get("/achievements").json()
    for e in entries:
        assert e["progress"] <= e["threshold"]
        assert e["progress_pct"] <= 100
