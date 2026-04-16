"""Tests for daily activity streak tracking."""
import sqlite3
import pytest
from datetime import date
from services.storage.db import init_db
from services.progression.streak import update_streak, get_streak


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()


def test_first_activity_sets_streak_to_one(db):
    update_streak(db, date(2026, 4, 15))
    db.commit()
    s = get_streak(db)
    assert s["current_streak"] == 1
    assert s["longest_streak"] == 1
    assert s["last_active_date"] == "2026-04-15"


def test_same_day_is_idempotent(db):
    update_streak(db, date(2026, 4, 15))
    update_streak(db, date(2026, 4, 15))
    db.commit()
    assert get_streak(db)["current_streak"] == 1


def test_consecutive_days_increment(db):
    update_streak(db, date(2026, 4, 14))
    db.commit()
    update_streak(db, date(2026, 4, 15))
    db.commit()
    s = get_streak(db)
    assert s["current_streak"] == 2
    assert s["longest_streak"] == 2


def test_gap_resets_streak(db):
    update_streak(db, date(2026, 4, 10))
    db.commit()
    update_streak(db, date(2026, 4, 12))   # skipped 11th
    db.commit()
    s = get_streak(db)
    assert s["current_streak"] == 1
    assert s["longest_streak"] == 1


def test_longest_streak_preserved_after_reset(db):
    for day in range(1, 6):                # 5-day streak
        update_streak(db, date(2026, 4, day))
        db.commit()
    update_streak(db, date(2026, 4, 10))   # gap → reset to 1
    db.commit()
    s = get_streak(db)
    assert s["current_streak"] == 1
    assert s["longest_streak"] == 5


def test_get_streak_before_any_activity(db):
    s = get_streak(db)
    assert s["current_streak"] == 0
    assert s["longest_streak"] == 0
    assert s["last_active_date"] is None
