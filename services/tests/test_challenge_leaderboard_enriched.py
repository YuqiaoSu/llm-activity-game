"""Tests for enriched GET /challenges/leaderboard?challenge_id=X."""
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient

from services.storage.db import init_db

_VISUAL = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                      "skin": None, "accessories": [], "anim_state": "idle"})


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES ('player_default', 'T', ?)",
        (_VISUAL,),
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


def _add_challenge(db, challenge_id="c1", threshold=100):
    db.execute(
        "INSERT INTO weekly_challenges (challenge_id, name, description, category,"
        " threshold, week_start, is_active) VALUES (?, 'T', 'D', 'WORK', ?, date('now', '-6 days'), 1)",
        (challenge_id, threshold),
    )
    db.commit()


def _set_progress(db, challenge_id, progress):
    from datetime import date, timedelta
    week_start = (date.today() - timedelta(days=date.today().weekday())).isoformat()
    db.execute(
        "INSERT OR REPLACE INTO player_weekly_progress"
        " (player_id, challenge_id, week_start, progress, completed)"
        " VALUES ('player_default', ?, ?, ?, ?)",
        (challenge_id, week_start, progress, 1 if progress >= 100 else 0),
    )
    db.commit()


def test_shape_has_pct_complete(client, db):
    _add_challenge(db, threshold=100)
    r = client.get("/challenges/leaderboard?challenge_id=c1")
    assert r.status_code == 200
    body = r.json()
    assert "player_pct_complete" in body
    for ghost in body["ghosts"]:
        assert "pct_complete" in ghost


def test_is_you_true_for_player(client, db):
    _add_challenge(db, threshold=100)
    body = client.get("/challenges/leaderboard?challenge_id=c1").json()
    assert body["is_you"] is True


def test_is_you_false_for_ghosts(client, db):
    _add_challenge(db, threshold=100)
    body = client.get("/challenges/leaderboard?challenge_id=c1").json()
    for ghost in body["ghosts"]:
        assert ghost["is_you"] is False


def test_pct_100_when_complete(client, db):
    _add_challenge(db, threshold=100)
    _set_progress(db, "c1", 100)
    body = client.get("/challenges/leaderboard?challenge_id=c1").json()
    assert body["player_pct_complete"] == 100.0


def test_pct_less_than_100_when_partial(client, db):
    _add_challenge(db, threshold=200)
    _set_progress(db, "c1", 100)
    body = client.get("/challenges/leaderboard?challenge_id=c1").json()
    assert body["player_pct_complete"] == 50.0


def test_404_on_unknown_challenge(client, db):
    r = client.get("/challenges/leaderboard?challenge_id=nonexistent")
    assert r.status_code == 404
