"""Tests for weekly challenge streak bonus."""
import json
import sqlite3
from datetime import datetime, timezone, date
import pytest
from fastapi.testclient import TestClient

from services.storage.db import init_db
from services.progression.weekly_challenges import get_week_start

_PLAYER = "player_default"


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    visual = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                         "skin": None, "accessories": [], "anim_state": "idle"})
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES (?, 'T', ?)",
        (_PLAYER, visual),
    )
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")
    conn.execute("INSERT OR IGNORE INTO streak_state (player_id) VALUES ('default')")
    conn.execute(
        "INSERT INTO weekly_challenges (challenge_id, name, description, category, metric, threshold)"
        " VALUES ('work_sprint', 'Work Sprint', 'desc', 'WORK', 'xp', 100)"
    )
    conn.execute(
        "INSERT INTO item_definitions (item_id, data) VALUES (?, ?)",
        ("rare_sword", json.dumps({"item_id": "rare_sword", "name": "Rare Sword",
                                   "rarity": "RARE", "category": "WORK",
                                   "description": "", "effects": []})),
    )
    conn.execute(
        "INSERT INTO player_category_xp (character_id, category, xp) VALUES (?, 'WORK', 999)",
        (_PLAYER,),
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    from services.api.main import create_app
    return TestClient(create_app(db=db))


def _ws() -> str:
    return get_week_start(datetime.now(timezone.utc))


def _mark_completed(db, challenge_id: str = "work_sprint") -> None:
    ws = _ws()
    db.execute(
        "INSERT OR REPLACE INTO player_weekly_progress"
        " (player_id, challenge_id, week_start, progress, completed, reward_given)"
        " VALUES ('player_default', ?, ?, 100, 1, 0)",
        (challenge_id, ws),
    )
    db.commit()


# ── GET /challenges/streak ────────────────────────────────────────────────────

def test_streak_shape(client):
    r = client.get("/challenges/streak")
    assert r.status_code == 200
    d = r.json()
    assert "current_streak" in d
    assert "longest_streak" in d
    assert "next_milestone_at" in d


def test_streak_zero_initially(client):
    r = client.get("/challenges/streak")
    assert r.json()["current_streak"] == 0
    assert r.json()["next_milestone_at"] == 3


# ── claim increments streak ───────────────────────────────────────────────────

def test_first_claim_sets_streak_to_1(client, db):
    _mark_completed(db)
    r = client.post("/challenges/work_sprint/claim")
    assert r.status_code == 200
    assert r.json()["challenge_streak"] == 1


def test_streak_in_get_after_claim(client, db):
    _mark_completed(db)
    client.post("/challenges/work_sprint/claim")
    r = client.get("/challenges/streak")
    assert r.json()["current_streak"] == 1


def test_second_claim_same_week_no_increment(client, db):
    _mark_completed(db)
    client.post("/challenges/work_sprint/claim")
    # Re-mark as unclaimed and claim again in same week
    db.execute(
        "UPDATE player_weekly_progress SET reward_given=0 WHERE player_id=? AND challenge_id='work_sprint'",
        (_PLAYER,),
    )
    db.commit()
    r = client.post("/challenges/work_sprint/claim")
    assert r.status_code == 200
    # streak should still be 1, not 2
    assert r.json()["challenge_streak"] == 1


def test_longest_streak_persists(client, db):
    _mark_completed(db)
    client.post("/challenges/work_sprint/claim")
    # Manually set streak back to 0 (simulate missed week + claim again)
    db.execute("UPDATE streak_state SET challenge_weekly_streak=0, last_challenge_week=NULL WHERE player_id='default'")
    db.commit()
    db.execute(
        "UPDATE player_weekly_progress SET reward_given=0 WHERE player_id=? AND challenge_id='work_sprint'",
        (_PLAYER,),
    )
    db.commit()
    client.post("/challenges/work_sprint/claim")
    r = client.get("/challenges/streak")
    assert r.json()["longest_streak"] == 1  # preserved from first claim


def test_milestone_3_awards_rare_item(client, db):
    # Force streak to 2, with last_challenge_week set to previous Monday
    from datetime import timedelta
    from services.progression.weekly_challenges import get_week_start
    current_ws = date.fromisoformat(get_week_start(datetime.now(timezone.utc)))
    prev_ws = (current_ws - timedelta(weeks=1)).isoformat()
    db.execute(
        "UPDATE streak_state SET challenge_weekly_streak=2, last_challenge_week=?"
        " WHERE player_id='default'",
        (prev_ws,),
    )
    db.commit()
    _mark_completed(db)
    r = client.post("/challenges/work_sprint/claim")
    assert r.status_code == 200
    assert r.json()["challenge_streak"] == 3
    # Item should be in inventory
    inv = db.execute(
        "SELECT item_id FROM inventory WHERE character_id=? AND item_id='rare_sword'",
        (_PLAYER,),
    ).fetchone()
    assert inv is not None
