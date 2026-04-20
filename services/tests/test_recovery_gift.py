"""Tests for streak recovery welcome-back gift item drop."""
import json
import sqlite3
from datetime import datetime, timezone, timedelta, date
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from services.storage.db import init_db

_PLAYER = "player_default"
_VISUAL = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                      "skin": None, "accessories": [], "anim_state": "idle"})

_CHUNKS = [
    {
        "chunk_id": "ck1", "label": "WORK", "confidence": 0.9,
        "duration_sec": 600, "time_of_day": "morning",
        "started_at": "2025-01-01T09:00:00Z", "ended_at": "2025-01-01T09:10:00Z",
    }
]


def _item_data(item_id: str) -> str:
    return json.dumps({"item_id": item_id, "name": item_id, "rarity": "COMMON",
                       "category": "WORK", "description": "", "effects": [],
                       "icon": "", "stackable": False, "set_id": None,
                       "drop_requirement": {"activity_label": None, "min_duration_sec": 0,
                                            "min_confidence": 0.0, "time_of_day": None}})


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
    conn.execute(
        "INSERT INTO player_category_xp (character_id, category, xp) VALUES (?, 'WORK', 10)",
        (_PLAYER,),
    )
    conn.execute("INSERT INTO item_definitions (item_id, data) VALUES ('welcome_item', ?)",
                 (_item_data("welcome_item"),))
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    from services.api.main import create_app
    return TestClient(create_app(db=db))


def _make_dormant(db):
    five_days_ago = (date.today() - timedelta(days=5)).isoformat()
    db.execute(
        "UPDATE streak_state SET last_active_date=? WHERE player_id='default'",
        (five_days_ago,),
    )
    db.commit()


def _has_recovery_gift_notification(db) -> bool:
    row = db.execute(
        "SELECT 1 FROM pending_notifications"
        " WHERE character_id=? AND event_type='recovery_gift'",
        (_PLAYER,),
    ).fetchone()
    return row is not None


def _inventory_count(db) -> int:
    row = db.execute(
        "SELECT COUNT(*) AS n FROM inventory WHERE character_id=?", (_PLAYER,)
    ).fetchone()
    return int(row["n"]) if row else 0


# ── recovery gift fires on dormancy return ────────────────────────────────────

def test_dormant_player_gets_gift(client, db):
    _make_dormant(db)
    with patch("services.sync_agent.tracker_client.TrackerClient.fetch_chunks",
               return_value=(_CHUNKS, "cursor1")):
        r = client.post("/sync/poll-now")
    assert r.status_code == 200
    # Item should be in inventory
    assert _inventory_count(db) >= 1


def test_dormant_player_gets_recovery_notification(client, db):
    _make_dormant(db)
    with patch("services.sync_agent.tracker_client.TrackerClient.fetch_chunks",
               return_value=(_CHUNKS, "cursor1")):
        client.post("/sync/poll-now")
    assert _has_recovery_gift_notification(db)


def test_non_dormant_player_no_gift_notification(client, db):
    # Not dormant — last_active_date = today
    db.execute(
        "UPDATE streak_state SET last_active_date=? WHERE player_id='default'",
        (date.today().isoformat(),),
    )
    db.commit()
    with patch("services.sync_agent.tracker_client.TrackerClient.fetch_chunks",
               return_value=(_CHUNKS, "cursor1")):
        client.post("/sync/poll-now")
    assert not _has_recovery_gift_notification(db)


def test_recovery_gift_reward_ledger_row(client, db):
    _make_dormant(db)
    with patch("services.sync_agent.tracker_client.TrackerClient.fetch_chunks",
               return_value=(_CHUNKS, "cursor1")):
        client.post("/sync/poll-now")
    row = db.execute(
        "SELECT 1 FROM reward_ledger WHERE chunk_id='recovery_gift'",
    ).fetchone()
    assert row is not None


def test_recovery_gift_idempotent_second_poll(client, db):
    _make_dormant(db)
    with patch("services.sync_agent.tracker_client.TrackerClient.fetch_chunks",
               return_value=(_CHUNKS, "cursor1")):
        client.post("/sync/poll-now")
    count_after_first = _inventory_count(db)
    # Second poll — no longer dormant, won't trigger again
    with patch("services.sync_agent.tracker_client.TrackerClient.fetch_chunks",
               return_value=([{**_CHUNKS[0], "chunk_id": "ck2"}], "cursor2")):
        client.post("/sync/poll-now")
    count_after_second = _inventory_count(db)
    # Second poll may award normal drops but recovery_gift ledger entry prevents duplicate
    ledger_rows = db.execute(
        "SELECT COUNT(*) AS n FROM reward_ledger WHERE chunk_id='recovery_gift'"
    ).fetchone()
    assert int(ledger_rows["n"]) == 1  # only one recovery gift


def test_recovery_gift_notification_event_type(client, db):
    _make_dormant(db)
    with patch("services.sync_agent.tracker_client.TrackerClient.fetch_chunks",
               return_value=(_CHUNKS, "cursor1")):
        client.post("/sync/poll-now")
    row = db.execute(
        "SELECT event_type FROM pending_notifications"
        " WHERE character_id=? AND event_type='recovery_gift'",
        (_PLAYER,),
    ).fetchone()
    assert row is not None
    assert row["event_type"] == "recovery_gift"
