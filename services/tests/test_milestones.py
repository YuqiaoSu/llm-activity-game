"""Tests for streak milestone drop rewards."""
from __future__ import annotations

import json
import sqlite3
import uuid
import pytest
from services.storage.db import init_db
from services.progression.milestones import (
    check_streak_milestone_drop,
    MILESTONE_INTERVAL,
    _milestone_chunk_id,
)


def _seed_item(conn, item_id: str, rarity: str, category: str = "WORK") -> None:
    conn.execute(
        "INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?, ?)",
        (item_id, json.dumps({
            "item_id": item_id, "name": item_id.replace("_", " ").title(),
            "rarity": rarity, "category": category,
            "icon": "", "effects": [], "drop_requirement": {}, "description": "",
        })),
    )


def _inventory_count(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM inventory").fetchone()[0]


def _ledger_count(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM reward_ledger").fetchone()[0]


def _notifications_count(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM pending_notifications").fetchone()[0]


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=OFF")
    init_db(conn)
    visual = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                         "skin": None, "accessories": [], "anim_state": "idle"})
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES ('player_default', 'T', ?)",
        (visual,),
    )
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")
    # Seed items at various rarities
    _seed_item(conn, "common_item",    "COMMON")
    _seed_item(conn, "uncommon_item",  "UNCOMMON")
    _seed_item(conn, "rare_item",      "RARE")
    _seed_item(conn, "epic_item",      "EPIC")
    _seed_item(conn, "legendary_item", "LEGENDARY")
    conn.commit()
    yield conn
    conn.close()


# ── milestone detection ───────────────────────────────────────────────────────

def test_non_milestone_streak_returns_false(db):
    for streak in [1, 2, 3, 4, 5, 6, 8, 13]:
        assert check_streak_milestone_drop(db, "player_default", streak) is False


def test_milestone_streak_returns_true(db):
    assert check_streak_milestone_drop(db, "player_default", MILESTONE_INTERVAL) is True


def test_milestone_multiples_all_trigger(db):
    for n in [7, 14, 21, 28]:
        db.commit()  # reset any in-progress state
        result = check_streak_milestone_drop(db, "player_default", n)
        assert result is True, f"streak {n} should trigger"


# ── rarity preference ─────────────────────────────────────────────────────────

def test_prefers_epic_over_rare_and_common(db):
    result = check_streak_milestone_drop(db, "player_default", 7)
    assert result is True
    row = db.execute(
        "SELECT d.data FROM inventory i "
        "JOIN item_definitions d ON i.item_id = d.item_id "
        "ORDER BY i.acquired_at DESC LIMIT 1"
    ).fetchone()
    assert row is not None
    item_data = json.loads(row["data"])
    assert item_data["rarity"] in ("EPIC", "LEGENDARY")


def test_falls_back_to_rare_when_no_epic(db):
    db.execute("DELETE FROM item_definitions WHERE item_id IN ('epic_item', 'legendary_item')")
    db.commit()
    result = check_streak_milestone_drop(db, "player_default", 7)
    assert result is True
    row = db.execute(
        "SELECT d.data FROM inventory i "
        "JOIN item_definitions d ON i.item_id = d.item_id LIMIT 1"
    ).fetchone()
    assert json.loads(row["data"])["rarity"] == "RARE"


# ── idempotency ───────────────────────────────────────────────────────────────

def test_same_milestone_not_granted_twice(db):
    check_streak_milestone_drop(db, "player_default", 7)
    db.commit()
    inv_before = _inventory_count(db)
    result2 = check_streak_milestone_drop(db, "player_default", 7)
    assert result2 is False
    assert _inventory_count(db) == inv_before


def test_different_milestones_both_granted(db):
    check_streak_milestone_drop(db, "player_default", 7)
    db.commit()
    check_streak_milestone_drop(db, "player_default", 14)
    db.commit()
    assert _inventory_count(db) == 2


# ── ledger and notification ───────────────────────────────────────────────────

def test_milestone_creates_ledger_entry(db):
    check_streak_milestone_drop(db, "player_default", 7)
    db.commit()
    assert _ledger_count(db) == 1
    chunk_id = db.execute("SELECT chunk_id FROM reward_ledger").fetchone()["chunk_id"]
    assert chunk_id == _milestone_chunk_id(7)


def test_milestone_creates_notification(db):
    check_streak_milestone_drop(db, "player_default", 7)
    db.commit()
    assert _notifications_count(db) == 1


def test_zero_streak_does_nothing(db):
    result = check_streak_milestone_drop(db, "player_default", 0)
    assert result is False
    assert _inventory_count(db) == 0


def test_empty_catalogue_returns_false(db):
    db.execute("DELETE FROM item_definitions")
    db.commit()
    result = check_streak_milestone_drop(db, "player_default", 7)
    assert result is False
