"""Tests for weekly challenge progress tracking and API endpoint."""
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
import pytest
from services.storage.db import init_db
from services.progression.weekly_challenges import get_week_start, update_weekly_progress
from services.seeds.weekly_challenges import SEED_WEEKLY_CHALLENGES


# ── fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    # Seed challenge definitions
    for ch in SEED_WEEKLY_CHALLENGES:
        conn.execute(
            "INSERT OR IGNORE INTO weekly_challenges "
            "(challenge_id, name, description, category, metric, threshold) VALUES (?, ?, ?, ?, ?, ?)",
            ch,
        )
    # Minimal player state
    visual = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                         "skin": None, "accessories": [], "anim_state": "idle"})
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES (?, ?, ?)",
        ("player_default", "Tester", visual),
    )
    conn.commit()
    yield conn
    conn.close()


def _insert_chunk_log(db, category: str) -> None:
    """Insert a chunk_log entry with now as processed_at."""
    db.execute(
        "INSERT OR IGNORE INTO chunk_log (log_id, chunk_id, category, xp_awarded, duration_sec, processed_at) "
        "VALUES (?, ?, ?, 10, 600, ?)",
        (str(uuid.uuid4()), str(uuid.uuid4()), category,
         datetime.now(timezone.utc).isoformat()),
    )
    db.commit()


# ── get_week_start ─────────────────────────────────────────────────────────────

def test_get_week_start_returns_monday():
    # 2026-04-15 is a Wednesday
    dt = datetime(2026, 4, 15, 10, 0, 0, tzinfo=timezone.utc)
    assert get_week_start(dt) == "2026-04-13"


def test_get_week_start_on_monday():
    dt = datetime(2026, 4, 13, 0, 0, 0, tzinfo=timezone.utc)
    assert get_week_start(dt) == "2026-04-13"


def test_get_week_start_on_sunday():
    dt = datetime(2026, 4, 19, 23, 59, 59, tzinfo=timezone.utc)
    assert get_week_start(dt) == "2026-04-13"


# ── xp metric ─────────────────────────────────────────────────────────────────

def test_xp_metric_increments_progress(db):
    result = update_weekly_progress(db, "player_default", {"WORK": 100})
    db.commit()
    week_start = get_week_start(datetime.now(timezone.utc))
    row = db.execute(
        "SELECT progress FROM player_weekly_progress "
        "WHERE player_id='player_default' AND challenge_id='work_sprint' AND week_start=?",
        (week_start,),
    ).fetchone()
    assert row is not None
    assert row["progress"] == 100


def test_xp_metric_accumulates_across_polls(db):
    update_weekly_progress(db, "player_default", {"WORK": 100})
    db.commit()
    update_weekly_progress(db, "player_default", {"WORK": 150})
    db.commit()
    week_start = get_week_start(datetime.now(timezone.utc))
    row = db.execute(
        "SELECT progress FROM player_weekly_progress "
        "WHERE player_id='player_default' AND challenge_id='work_sprint' AND week_start=?",
        (week_start,),
    ).fetchone()
    assert row["progress"] == 250


def test_xp_metric_below_threshold_not_completed(db):
    result = update_weekly_progress(db, "player_default", {"WORK": 299})
    db.commit()
    assert "work_sprint" not in result
    week_start = get_week_start(datetime.now(timezone.utc))
    row = db.execute(
        "SELECT completed FROM player_weekly_progress "
        "WHERE player_id='player_default' AND challenge_id='work_sprint' AND week_start=?",
        (week_start,),
    ).fetchone()
    assert row["completed"] == 0


def test_xp_metric_completes_at_threshold(db):
    result = update_weekly_progress(db, "player_default", {"WORK": 300})
    db.commit()
    assert "work_sprint" in result


def test_xp_metric_completion_fires_notification(db):
    update_weekly_progress(db, "player_default", {"WORK": 300})
    db.commit()
    row = db.execute(
        "SELECT payload FROM pending_notifications "
        "WHERE character_id='player_default' AND event_type='challenge_complete'"
    ).fetchone()
    assert row is not None
    payload = json.loads(row["payload"])
    assert payload["challenge_id"] == "work_sprint"
    assert payload["name"] == "Work Sprint"


# ── total_xp metric ───────────────────────────────────────────────────────────

def test_total_xp_metric_sums_all_categories(db):
    result = update_weekly_progress(db, "player_default", {"WORK": 300, "CREATIVE": 200})
    db.commit()
    assert "big_week" in result


def test_total_xp_metric_below_threshold(db):
    result = update_weekly_progress(db, "player_default", {"WORK": 200, "CREATIVE": 100})
    db.commit()
    assert "big_week" not in result


# ── categories metric ─────────────────────────────────────────────────────────

def test_categories_metric_counts_distinct_categories(db):
    _insert_chunk_log(db, "WORK")
    _insert_chunk_log(db, "CREATIVE")
    _insert_chunk_log(db, "LEARNING")
    result = update_weekly_progress(db, "player_default", {"WORK": 10})
    db.commit()
    assert "variety_pack" in result


def test_categories_metric_below_threshold(db):
    _insert_chunk_log(db, "WORK")
    _insert_chunk_log(db, "CREATIVE")
    result = update_weekly_progress(db, "player_default", {"WORK": 10})
    db.commit()
    assert "variety_pack" not in result


# ── idempotency ────────────────────────────────────────────────────────────────

def test_already_completed_challenge_not_returned_again(db):
    first = update_weekly_progress(db, "player_default", {"WORK": 300})
    db.commit()
    assert "work_sprint" in first

    second = update_weekly_progress(db, "player_default", {"WORK": 300})
    db.commit()
    assert "work_sprint" not in second


def test_notification_created_only_once(db):
    # First poll completes work_sprint (300 >= threshold 300)
    update_weekly_progress(db, "player_default", {"WORK": 300})
    db.commit()
    # Second poll adds minimal XP — work_sprint already completed, must not re-fire
    update_weekly_progress(db, "player_default", {"WORK": 1})
    db.commit()
    count = db.execute(
        "SELECT COUNT(*) FROM pending_notifications "
        "WHERE character_id='player_default' AND event_type='challenge_complete' "
        "AND json_extract(payload, '$.challenge_id') = 'work_sprint'"
    ).fetchone()[0]
    assert count == 1


# ── empty input ───────────────────────────────────────────────────────────────

def test_empty_xp_by_category_returns_empty(db):
    result = update_weekly_progress(db, "player_default", {})
    assert result == []


# ── API endpoint ──────────────────────────────────────────────────────────────

def test_get_challenges_returns_all(db):
    from fastapi.testclient import TestClient
    from services.api.main import create_app
    app = create_app(db=db)
    client = TestClient(app)

    r = client.get("/challenges")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == len(SEED_WEEKLY_CHALLENGES)
    assert all(item["progress"] == 0 for item in data)
    assert all(item["completed"] is False for item in data)


def test_get_challenges_shows_progress_and_completion(db):
    from fastapi.testclient import TestClient
    from services.api.main import create_app

    update_weekly_progress(db, "player_default", {"WORK": 300})
    db.commit()

    app = create_app(db=db)
    client = TestClient(app)
    r = client.get("/challenges")
    assert r.status_code == 200
    by_id = {item["challenge_id"]: item for item in r.json()}
    assert by_id["work_sprint"]["progress"] == 300
    assert by_id["work_sprint"]["completed"] is True
    assert by_id["creative_flow"]["completed"] is False
