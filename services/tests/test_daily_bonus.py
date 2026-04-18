"""Tests for GET /challenges/daily-bonus and the 2× XP multiplier on claim."""
import hashlib
import json
import sqlite3
from datetime import date

import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
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
    for cid, cat in [("work_sprint", "WORK"), ("creative_flow", "CREATIVE"), ("learn_fast", "LEARN")]:
        conn.execute(
            "INSERT INTO weekly_challenges (challenge_id, name, description, category, metric, threshold)"
            " VALUES (?, ?, ?, ?, 'xp', 300)",
            (cid, cid.replace("_", " ").title(), f"Earn 300 {cat} XP", cat),
        )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    return TestClient(create_app(db=db))


def _today_bonus_id(db) -> str:
    rows = db.execute(
        "SELECT challenge_id FROM weekly_challenges ORDER BY challenge_id"
    ).fetchall()
    today_key = date.today().isoformat().encode()
    index = int(hashlib.md5(today_key).hexdigest(), 16) % len(rows)
    return rows[index]["challenge_id"]


def _mark_completed(db, challenge_id: str) -> None:
    ws = get_week_start(datetime.now(timezone.utc))
    db.execute(
        "INSERT OR REPLACE INTO player_weekly_progress"
        " (player_id, challenge_id, week_start, progress, completed, reward_given)"
        " VALUES ('player_default', ?, ?, 300, 1, 0)",
        (challenge_id, ws),
    )
    db.commit()


# ── GET /challenges/daily-bonus ──────────────────────────────────────────────

def test_daily_bonus_returns_200(client):
    resp = client.get("/challenges/daily-bonus")
    assert resp.status_code == 200


def test_daily_bonus_shape(client):
    data = client.get("/challenges/daily-bonus").json()
    for key in ("challenge_id", "name", "description", "category", "multiplier", "date"):
        assert key in data


def test_daily_bonus_multiplier_is_2(client):
    data = client.get("/challenges/daily-bonus").json()
    assert data["multiplier"] == 2.0


def test_daily_bonus_date_is_today(client):
    data = client.get("/challenges/daily-bonus").json()
    assert data["date"] == date.today().isoformat()


def test_daily_bonus_is_deterministic(client):
    r1 = client.get("/challenges/daily-bonus").json()["challenge_id"]
    r2 = client.get("/challenges/daily-bonus").json()["challenge_id"]
    assert r1 == r2


def test_daily_bonus_id_matches_hash_formula(client, db):
    expected = _today_bonus_id(db)
    actual = client.get("/challenges/daily-bonus").json()["challenge_id"]
    assert actual == expected


# ── Claim with daily-bonus multiplier ────────────────────────────────────────

def test_claim_daily_bonus_awards_double_xp(client, db):
    bonus_id = _today_bonus_id(db)
    _mark_completed(db, bonus_id)
    resp = client.post(f"/challenges/{bonus_id}/claim")
    assert resp.status_code == 200
    data = resp.json()
    assert data["xp_awarded"] == 100  # 50 × 2
    assert data["daily_bonus"] is True


def test_claim_non_bonus_awards_base_xp(client, db):
    all_ids = [r["challenge_id"] for r in db.execute(
        "SELECT challenge_id FROM weekly_challenges ORDER BY challenge_id"
    ).fetchall()]
    bonus_id = _today_bonus_id(db)
    non_bonus = next(c for c in all_ids if c != bonus_id)
    _mark_completed(db, non_bonus)
    resp = client.post(f"/challenges/{non_bonus}/claim")
    assert resp.status_code == 200
    data = resp.json()
    assert data["xp_awarded"] == 50
    assert data["daily_bonus"] is False
