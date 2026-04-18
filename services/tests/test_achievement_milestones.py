"""Tests for check_and_unlock_milestones() in achievement_milestones.py."""
import json
import sqlite3
from datetime import datetime, timezone

import pytest

from services.storage.db import init_db
from services.progression.achievement_milestones import check_and_unlock_milestones


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    visual = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                         "skin": None, "accessories": [], "anim_state": "idle"})
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES ('player_default', 'T', ?)",
        (visual,),
    )
    conn.execute("INSERT OR IGNORE INTO streak_state (player_id) VALUES ('default')")
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")
    conn.commit()
    yield conn
    conn.close()


def _set_total_xp(db, xp: int) -> None:
    db.execute(
        "INSERT OR REPLACE INTO player_category_xp (character_id, category, xp)"
        " VALUES ('player_default', 'WORK', ?)",
        (xp,),
    )
    db.commit()


def _set_streak(db, days: int) -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    db.execute(
        "UPDATE streak_state SET current_streak=?, last_active_date=? WHERE player_id='default'",
        (days, today),
    )
    db.commit()


def _add_item(db, item_id: str = "test_item") -> None:
    import uuid
    db.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk)"
        " VALUES (?, 'player_default', ?, datetime('now'), 'chunk_test')",
        (str(uuid.uuid4()), item_id),
    )
    db.commit()


def _unlocked_ids(db) -> set[str]:
    return {r["achievement_id"] for r in db.execute(
        "SELECT achievement_id FROM player_achievements WHERE player_id='player_default'"
    ).fetchall()}


# ── Basic behaviour ───────────────────────────────────────────────────────────

def test_no_milestones_at_zero_stats(db):
    result = check_and_unlock_milestones(db)
    assert result == []


def test_returns_list(db):
    assert isinstance(check_and_unlock_milestones(db), list)


def test_milestones_inserted_into_achievements_table(db):
    check_and_unlock_milestones(db)
    rows = db.execute("SELECT achievement_id FROM achievements").fetchall()
    ids = {r["achievement_id"] for r in rows}
    assert "first_drop" in ids
    assert "level_5_milestone" in ids
    assert "streak_warrior" in ids


# ── Individual milestone triggers ────────────────────────────────────────────

def test_first_drop_unlocked_when_item_collected(db):
    _add_item(db)
    result = check_and_unlock_milestones(db)
    assert "first_drop" in result


def test_xp_1000_unlocked_at_threshold(db):
    _set_total_xp(db, 1000)
    result = check_and_unlock_milestones(db)
    assert "xp_1000" in result


def test_xp_1000_not_unlocked_below_threshold(db):
    _set_total_xp(db, 999)
    result = check_and_unlock_milestones(db)
    assert "xp_1000" not in result


def test_streak_warrior_unlocked_at_14(db):
    _set_streak(db, 14)
    result = check_and_unlock_milestones(db)
    assert "streak_warrior" in result


def test_streak_warrior_not_unlocked_at_13(db):
    _set_streak(db, 13)
    result = check_and_unlock_milestones(db)
    assert "streak_warrior" not in result


# ── Idempotency ───────────────────────────────────────────────────────────────

def test_no_double_unlock(db):
    _add_item(db)
    first = check_and_unlock_milestones(db)
    db.commit()
    second = check_and_unlock_milestones(db)
    assert "first_drop" in first
    assert "first_drop" not in second


def test_notification_emitted_on_unlock(db):
    _add_item(db)
    check_and_unlock_milestones(db)
    db.commit()
    notifs = db.execute(
        "SELECT * FROM pending_notifications WHERE event_type='achievement_unlock'"
    ).fetchall()
    assert len(notifs) >= 1


def test_achievement_stored_in_player_achievements(db):
    _set_total_xp(db, 1000)
    check_and_unlock_milestones(db)
    db.commit()
    assert "xp_1000" in _unlocked_ids(db)
