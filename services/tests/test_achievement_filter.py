"""Tests for GET /achievements with unlocked and search filter params."""
import sqlite3
import pytest
from fastapi.testclient import TestClient

from services.storage.db import init_db, bootstrap_defaults
from services.api.main import app


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    bootstrap_defaults(conn)
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    app.state.db = db
    return TestClient(app)


def _seed_achievement(db, aid: str, name: str, condition_type: str = "total_xp", threshold: int = 100) -> None:
    db.execute(
        "INSERT OR IGNORE INTO achievements (achievement_id, name, description, condition_type, threshold)"
        " VALUES (?, ?, '', ?, ?)",
        (aid, name, condition_type, threshold),
    )
    db.commit()


def _unlock(db, aid: str) -> None:
    from datetime import datetime, timezone
    db.execute(
        "INSERT OR IGNORE INTO player_achievements (player_id, achievement_id, unlocked_at)"
        " VALUES ('player_default', ?, ?)",
        (aid, datetime.now(timezone.utc).isoformat()),
    )
    db.commit()


def test_no_filter_returns_all(client, db):
    _seed_achievement(db, "a1", "Alpha")
    _seed_achievement(db, "a2", "Beta")
    _unlock(db, "a1")
    items = client.get("/achievements").json()
    ids = {i["achievement_id"] for i in items}
    assert "a1" in ids and "a2" in ids


def test_unlocked_true_returns_only_unlocked(client, db):
    _seed_achievement(db, "unlocked_1", "Got it")
    _seed_achievement(db, "locked_1",   "Not yet")
    _unlock(db, "unlocked_1")
    items = client.get("/achievements?unlocked=true").json()
    assert all(i["unlocked"] for i in items)
    ids = {i["achievement_id"] for i in items}
    assert "unlocked_1" in ids
    assert "locked_1" not in ids


def test_unlocked_false_returns_only_locked(client, db):
    _seed_achievement(db, "unlocked_2", "Done")
    _seed_achievement(db, "locked_2",   "Pending")
    _unlock(db, "unlocked_2")
    items = client.get("/achievements?unlocked=false").json()
    assert all(not i["unlocked"] for i in items)
    ids = {i["achievement_id"] for i in items}
    assert "locked_2" in ids
    assert "unlocked_2" not in ids


def test_search_returns_matching_name(client, db):
    _seed_achievement(db, "s1", "Streak Master")
    _seed_achievement(db, "s2", "XP Collector")
    items = client.get("/achievements?search=streak").json()
    names = [i["name"] for i in items]
    assert any("Streak" in n for n in names)
    assert not any("XP Collector" in n for n in names)


def test_search_no_match_returns_empty(client, db):
    _seed_achievement(db, "s3", "Known Achievement")
    items = client.get("/achievements?search=zzznomatch").json()
    assert items == [] or not any("Known" in i["name"] for i in items)


def test_search_is_case_insensitive(client, db):
    _seed_achievement(db, "s4", "Dragon Slayer")
    items_lower = client.get("/achievements?search=dragon").json()
    items_upper = client.get("/achievements?search=DRAGON").json()
    assert len(items_lower) == len(items_upper)
