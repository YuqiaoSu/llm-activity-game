"""Tests for GET /goals/streak and POST /goals/claim-streak-reward endpoints."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.storage.db import init_db


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
        "INSERT INTO player_profile (character_id, name, visual) VALUES ('player_default','T',?)",
        (visual,),
    )
    conn.execute("INSERT OR IGNORE INTO streak_state (player_id) VALUES ('default')")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    return TestClient(create_app(db=db))


def _set_streak(db, streak: int) -> None:
    db.execute(
        "UPDATE streak_state SET goal_streak=? WHERE player_id='default'", (streak,)
    )
    db.commit()


def _add_item_def(db, item_id: str, rarity: str) -> None:
    data = json.dumps({"name": item_id, "category": "WORK", "rarity": rarity,
                       "description": "", "effects": []})
    db.execute("INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?,?)",
               (item_id, data))
    db.commit()


def _add_completed_goal(db) -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    db.execute(
        "INSERT OR IGNORE INTO daily_goals "
        "(goal_id, player_id, date, category, target_sec, progress_sec, completed, created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), "player_default", today, "WORK", 1200, 1200, 1,
         datetime.now(timezone.utc).isoformat()),
    )
    db.commit()


# ── GET /goals/streak ─────────────────────────────────────────────────────────

def test_get_streak_zero_at_start(client):
    resp = client.get("/goals/streak")
    assert resp.status_code == 200
    data = resp.json()
    assert data["goal_streak"] == 0
    assert data["next_milestone_at"] == 7
    assert data["days_to_milestone"] == 7


def test_get_streak_reflects_stored_value(client, db):
    _set_streak(db, 5)
    data = client.get("/goals/streak").json()
    assert data["goal_streak"] == 5
    assert data["next_milestone_at"] == 7
    assert data["days_to_milestone"] == 2


def test_get_streak_past_7_milestone(client, db):
    _set_streak(db, 8)
    data = client.get("/goals/streak").json()
    assert data["goal_streak"] == 8
    assert data["next_milestone_at"] == 14
    assert data["days_to_milestone"] == 6


def test_get_streak_past_all_milestones(client, db):
    _set_streak(db, 30)
    data = client.get("/goals/streak").json()
    assert data["next_milestone_at"] is None
    assert data["days_to_milestone"] is None


def test_get_streak_milestones_shape(client):
    data = client.get("/goals/streak").json()
    milestones = data["milestones"]
    assert isinstance(milestones, list)
    assert len(milestones) == 3
    days_list = [m["days"] for m in milestones]
    assert days_list == [7, 14, 30]
    rarities = [m["rarity"] for m in milestones]
    assert "RARE" in rarities
    assert "EPIC" in rarities
    assert "LEGENDARY" in rarities


def test_get_streak_reached_flags(client, db):
    _set_streak(db, 10)
    milestones = client.get("/goals/streak").json()["milestones"]
    by_days = {m["days"]: m for m in milestones}
    assert by_days[7]["reached"] is True
    assert by_days[14]["reached"] is False
    assert by_days[30]["reached"] is False


# ── POST /goals/claim-streak-reward ──────────────────────────────────────────

def test_claim_reward_no_goals_no_grant(client):
    resp = client.post("/goals/claim-streak-reward")
    assert resp.status_code == 200
    data = resp.json()
    assert data["reward_granted"] is False


def test_claim_reward_on_milestone_grants_item(client, db):
    _add_item_def(db, "rare_gem", "RARE")
    _set_streak(db, 6)
    _add_completed_goal(db)
    resp = client.post("/goals/claim-streak-reward")
    assert resp.status_code == 200
    data = resp.json()
    assert data["reward_granted"] is True
    assert data["goal_streak"] == 7
    inv = db.execute(
        "SELECT COUNT(*) AS n FROM inventory WHERE character_id='player_default'"
    ).fetchone()
    assert inv["n"] >= 1


def test_claim_reward_idempotent(client, db):
    _add_item_def(db, "rare_gem", "RARE")
    _set_streak(db, 6)
    _add_completed_goal(db)
    resp1 = client.post("/goals/claim-streak-reward")
    resp2 = client.post("/goals/claim-streak-reward")
    assert resp1.json()["reward_granted"] is True
    assert resp2.json()["reward_granted"] is False


def test_claim_reward_response_has_streak_fields(client):
    resp = client.post("/goals/claim-streak-reward")
    data = resp.json()
    assert "reward_granted" in data
    assert "goal_streak" in data
    assert "next_milestone_at" in data
    assert "milestones" in data
