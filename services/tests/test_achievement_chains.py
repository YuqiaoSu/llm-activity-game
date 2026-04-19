"""Tests for achievement chain fields (parent_achievement_id, chain_depth, chain_complete)."""
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
    bootstrap_defaults(conn)   # seeds achievements + chain parents
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    app.state.db = db
    return TestClient(app)


def _unlock(db, aid: str) -> None:
    from datetime import datetime, timezone
    db.execute(
        "INSERT OR IGNORE INTO player_achievements (player_id, achievement_id, unlocked_at)"
        " VALUES ('player_default', ?, ?)",
        (aid, datetime.now(timezone.utc).isoformat()),
    )
    db.commit()


def _get_by_id(client, aid: str) -> dict | None:
    items = client.get("/achievements").json()
    return next((i for i in items if i["achievement_id"] == aid), None)


# ── field presence ────────────────────────────────────────────────────────────

def test_parent_achievement_id_field_present(client):
    items = client.get("/achievements").json()
    assert len(items) > 0
    for item in items:
        assert "parent_achievement_id" in item
        assert "chain_depth" in item
        assert "chain_complete" in item


def test_root_achievement_has_null_parent(client):
    item = _get_by_id(client, "first_blood")
    assert item is not None
    assert item["parent_achievement_id"] is None


def test_chain_child_has_correct_parent(client):
    item = _get_by_id(client, "getting_warmed_up")
    assert item is not None
    assert item["parent_achievement_id"] == "first_blood"


# ── chain_depth ───────────────────────────────────────────────────────────────

def test_root_has_depth_zero(client):
    item = _get_by_id(client, "first_blood")
    assert item["chain_depth"] == 0


def test_child_has_depth_one(client):
    item = _get_by_id(client, "getting_warmed_up")
    assert item["chain_depth"] == 1


def test_grandchild_has_depth_two(client):
    item = _get_by_id(client, "dedicated")
    assert item["chain_depth"] == 2


# ── chain_complete ────────────────────────────────────────────────────────────

def test_chain_complete_false_when_parent_locked(client, db):
    item = _get_by_id(client, "getting_warmed_up")
    assert item["chain_complete"] is False   # first_blood not unlocked


def test_chain_complete_true_when_all_ancestors_unlocked(client, db):
    _unlock(db, "first_blood")
    item = _get_by_id(client, "getting_warmed_up")
    assert item["chain_complete"] is True


def test_grandchild_complete_requires_all_ancestors(client, db):
    _unlock(db, "first_blood")
    # getting_warmed_up still locked → dedicated's chain_complete = False
    item = _get_by_id(client, "dedicated")
    assert item["chain_complete"] is False
    _unlock(db, "getting_warmed_up")
    item = _get_by_id(client, "dedicated")
    assert item["chain_complete"] is True


def test_level_chain_parents_correct(client):
    level_5 = _get_by_id(client, "level_5")
    level_10 = _get_by_id(client, "level_10")
    assert level_5["parent_achievement_id"] == "first_level"
    assert level_10["parent_achievement_id"] == "level_5"
    assert level_5["chain_depth"] == 1
    assert level_10["chain_depth"] == 2


def test_items_chain_parents_correct(client):
    collector = _get_by_id(client, "collector")
    hoarder   = _get_by_id(client, "hoarder")
    assert collector["parent_achievement_id"] == "first_item"
    assert hoarder["parent_achievement_id"] == "collector"
