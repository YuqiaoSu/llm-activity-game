"""Tests for GET /suggestions (smart quest suggestion engine)."""
import json
import sqlite3
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient
from services.storage.db import init_db
from services.progression.suggestions import get_suggestions


# ── fixtures ──────────────────────────────────────────────────────────────────

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
    conn.execute("INSERT OR IGNORE INTO streak_state (player_id) VALUES ('default')")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    from services.api.main import create_app
    return TestClient(create_app(db=db))


def _add_chunk(db, category: str, duration_sec: int = 1800, days_ago: int = 0) -> None:
    """Insert a chunk_log row `days_ago` days in the past."""
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    import uuid
    db.execute(
        "INSERT OR IGNORE INTO chunk_log "
        "(log_id, chunk_id, category, xp_awarded, duration_sec, processed_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), str(uuid.uuid4()), category, duration_sec // 60, duration_sec, ts),
    )
    db.commit()


def _add_xp(db, category: str, xp: int) -> None:
    db.execute(
        "INSERT INTO player_category_xp (character_id, category, xp) VALUES ('player_default', ?, ?) "
        "ON CONFLICT (character_id, category) DO UPDATE SET xp = xp + excluded.xp",
        (category, xp),
    )
    db.commit()


def _set_streak(db, current: int, last_date: str) -> None:
    db.execute(
        "UPDATE streak_state SET current_streak=?, last_active_date=? WHERE player_id='default'",
        (current, last_date),
    )
    db.commit()


# ── endpoint ──────────────────────────────────────────────────────────────────

def test_suggestions_endpoint_returns_list(client):
    data = client.get("/suggestions").json()
    assert isinstance(data, list)


def test_suggestions_all_fields_present(client, db):
    _add_xp(db, "WORK", 100)
    data = client.get("/suggestions").json()
    for s in data:
        assert "type" in s
        assert "category" in s
        assert "text" in s
        assert "target_min" in s
        assert "priority" in s


# ── streak danger ─────────────────────────────────────────────────────────────

def test_streak_danger_included_when_streak_active_but_no_activity_today(db):
    yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
    _set_streak(db, current=5, last_date=yesterday)
    suggestions = get_suggestions(db)
    types = [s["type"] for s in suggestions]
    assert "streak_danger" in types


def test_streak_danger_not_included_when_active_today(db):
    today = datetime.now(timezone.utc).date().isoformat()
    _set_streak(db, current=3, last_date=today)
    suggestions = get_suggestions(db)
    types = [s["type"] for s in suggestions]
    assert "streak_danger" not in types


def test_streak_danger_not_included_when_no_streak(db):
    _set_streak(db, current=0, last_date=None)
    suggestions = get_suggestions(db)
    types = [s["type"] for s in suggestions]
    assert "streak_danger" not in types


def test_streak_danger_has_highest_priority(db):
    yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
    _set_streak(db, current=7, last_date=yesterday)
    suggestions = get_suggestions(db)
    streak_s = next(s for s in suggestions if s["type"] == "streak_danger")
    assert streak_s["priority"] == 0


# ── gap suggestions ───────────────────────────────────────────────────────────

def test_gap_suggestion_for_category_with_no_recent_activity(db):
    # WORK has all-time XP but no recent chunks → should appear as gap
    _add_xp(db, "WORK", 200)
    # No recent chunk_log rows for WORK
    suggestions = get_suggestions(db)
    gap_cats = [s["category"] for s in suggestions if s["type"] == "gap"]
    assert "WORK" in gap_cats


def test_gap_suggestion_not_for_category_active_recently(db):
    _add_xp(db, "GAME", 100)
    _add_chunk(db, "GAME", duration_sec=1800, days_ago=0)
    suggestions = get_suggestions(db)
    gap_cats = [s["category"] for s in suggestions if s["type"] == "gap"]
    assert "GAME" not in gap_cats


def test_gap_suggestion_text_mentions_days_window(db):
    _add_xp(db, "EXPLORE", 50)
    suggestions = get_suggestions(db)
    gap_s = next((s for s in suggestions if s["type"] == "gap" and s["category"] == "EXPLORE"), None)
    assert gap_s is not None
    assert "7 days" in gap_s["text"]


def test_gap_suggestion_for_never_tried_category(db):
    # No XP at all → should get "never logged" variant
    suggestions = get_suggestions(db)
    gap_s = next((s for s in suggestions if s["type"] == "gap"), None)
    assert gap_s is not None
    assert "never" in gap_s["text"].lower() or "haven't" in gap_s["text"].lower()


# ── challenge nudge ───────────────────────────────────────────────────────────

def _seed_challenge(db, challenge_id: str = "ch1", description: str = "Do 30 min WORK",
                    threshold: int = 30) -> None:
    db.execute(
        "INSERT OR IGNORE INTO weekly_challenges "
        "(challenge_id, name, description, category, metric, threshold) "
        "VALUES (?, ?, ?, 'WORK', 'xp', ?)",
        (challenge_id, description, description, threshold),
    )
    db.commit()


def test_challenge_nudge_appears_when_incomplete_challenge_exists(db):
    _seed_challenge(db)
    suggestions = get_suggestions(db)
    types = [s["type"] for s in suggestions]
    assert "challenge_nudge" in types


def test_challenge_nudge_text_contains_description(db):
    _seed_challenge(db, description="Work 45 minutes")
    suggestions = get_suggestions(db)
    nudge = next(s for s in suggestions if s["type"] == "challenge_nudge")
    assert "Work 45 minutes" in nudge["text"]


# ── diversify suggestion ──────────────────────────────────────────────────────

def test_diversify_suggestion_when_one_category_dominates(db):
    # WORK = 90% of recent time
    _add_xp(db, "WORK", 500)
    _add_xp(db, "GAME", 100)
    _add_chunk(db, "WORK", duration_sec=5400)   # 90 min
    _add_chunk(db, "GAME", duration_sec=600)    # 10 min
    suggestions = get_suggestions(db)
    types = [s["type"] for s in suggestions]
    assert "diversify" in types


def test_no_diversify_when_categories_balanced(db):
    _add_xp(db, "WORK", 200)
    _add_xp(db, "GAME", 200)
    _add_chunk(db, "WORK", duration_sec=1800)
    _add_chunk(db, "GAME", duration_sec=1800)
    suggestions = get_suggestions(db)
    types = [s["type"] for s in suggestions]
    assert "diversify" not in types


# ── max limit ─────────────────────────────────────────────────────────────────

def test_max_five_suggestions_returned(db):
    # Set up conditions that could trigger many suggestions
    yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
    _set_streak(db, current=5, last_date=yesterday)
    for cat in ["WORK", "GAME", "EXPLORE"]:
        _add_xp(db, cat, 100)
    _seed_challenge(db)
    suggestions = get_suggestions(db)
    assert len(suggestions) <= 5
