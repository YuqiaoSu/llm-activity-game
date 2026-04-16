"""Tests for challenge claim and reroll endpoints."""
import sqlite3
import json
import pytest
from fastapi.testclient import TestClient
from services.storage.db import init_db
from services.progression.weekly_challenges import get_week_start
from datetime import datetime, timezone


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
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")
    conn.execute("INSERT OR IGNORE INTO streak_state (player_id) VALUES ('default')")
    # Seed one challenge
    conn.execute(
        "INSERT INTO weekly_challenges (challenge_id, name, description, category, metric, threshold) "
        "VALUES ('work_sprint', 'Work Sprint', 'Earn 300 WORK XP', 'WORK', 'xp', 300)"
    )
    conn.execute(
        "INSERT INTO weekly_challenges (challenge_id, name, description, category, metric, threshold) "
        "VALUES ('creative_flow', 'Creative Flow', 'Earn 200 CREATIVE XP', 'CREATIVE', 'xp', 200)"
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    from services.api.main import create_app
    return TestClient(create_app(db=db))


def _week_start() -> str:
    return get_week_start(datetime.now(timezone.utc))


def _mark_completed(db, challenge_id: str) -> None:
    ws = _week_start()
    db.execute(
        """
        INSERT OR REPLACE INTO player_weekly_progress
            (player_id, challenge_id, week_start, progress, completed, reward_given)
        VALUES ('player_default', ?, ?, 300, 1, 0)
        """,
        (challenge_id, ws),
    )
    db.commit()


# ── claim ─────────────────────────────────────────────────────────────────────

def test_claim_completed_challenge(client, db):
    _mark_completed(db, "work_sprint")
    r = client.post("/challenges/work_sprint/claim")
    assert r.status_code == 200
    data = r.json()
    assert data["challenge_id"] == "work_sprint"
    assert data["xp_awarded"] == 50
    assert data["category"] == "WORK"


def test_claim_awards_xp_to_db(client, db):
    _mark_completed(db, "work_sprint")
    client.post("/challenges/work_sprint/claim")
    row = db.execute(
        "SELECT xp FROM player_category_xp WHERE character_id='player_default' AND category='WORK'"
    ).fetchone()
    assert row is not None
    assert row["xp"] == 50


def test_claim_sets_reward_given(client, db):
    _mark_completed(db, "work_sprint")
    client.post("/challenges/work_sprint/claim")
    row = db.execute(
        "SELECT reward_given FROM player_weekly_progress "
        "WHERE player_id='player_default' AND challenge_id='work_sprint'"
    ).fetchone()
    assert row["reward_given"] == 1


def test_claim_not_completed_returns_409(client, db):
    r = client.post("/challenges/work_sprint/claim")
    assert r.status_code == 409


def test_claim_nonexistent_challenge_returns_404(client):
    r = client.post("/challenges/no_such_challenge/claim")
    assert r.status_code == 404


def test_claim_already_claimed_returns_409(client, db):
    _mark_completed(db, "work_sprint")
    client.post("/challenges/work_sprint/claim")
    r = client.post("/challenges/work_sprint/claim")
    assert r.status_code == 409
    assert "already" in r.json()["detail"].lower()


# ── reroll ────────────────────────────────────────────────────────────────────

def test_reroll_returns_challenge(client):
    r = client.post("/challenges/reroll")
    assert r.status_code == 200
    data = r.json()
    assert "rerolled_challenge_id" in data
    assert data["progress"] == 0
    assert data["completed"] is False


def test_reroll_records_reroll_state(client, db):
    client.post("/challenges/reroll")
    ws = _week_start()
    row = db.execute(
        "SELECT * FROM weekly_reroll_state WHERE player_id='player_default' AND week_start=?",
        (ws,),
    ).fetchone()
    assert row is not None


def test_reroll_twice_returns_409(client):
    client.post("/challenges/reroll")
    r = client.post("/challenges/reroll")
    assert r.status_code == 409
    assert "already" in r.json()["detail"].lower()


def test_reroll_clears_progress(client, db):
    ws = _week_start()
    db.execute(
        "INSERT INTO player_weekly_progress "
        "(player_id, challenge_id, week_start, progress, completed, reward_given) "
        "VALUES ('player_default', 'work_sprint', ?, 100, 0, 0)",
        (ws,),
    )
    db.commit()
    r = client.post("/challenges/reroll")
    assert r.status_code == 200
    rerolled = r.json()["rerolled_challenge_id"]
    row = db.execute(
        "SELECT progress FROM player_weekly_progress "
        "WHERE player_id='player_default' AND challenge_id=? AND week_start=?",
        (rerolled, ws),
    ).fetchone()
    # Row should be deleted (None) or have progress=0
    assert row is None or row["progress"] == 0


def test_reroll_all_completed_returns_409(client, db):
    # Complete both challenges
    _mark_completed(db, "work_sprint")
    _mark_completed(db, "creative_flow")
    r = client.post("/challenges/reroll")
    assert r.status_code == 409
