"""Tests for skill upgrade tiers — POST /skills/{id}/upgrade and effect scaling."""
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.storage.db import init_db, bootstrap_defaults
from services.place_service.effects import load_skill_effects
from services.progression.xp import award_category_xp
from services.models.enums import Category


def _seed_skill(db, skill_id="test_skill", xp_cost=100, max_level=3):
    db.execute(
        "INSERT OR IGNORE INTO skills (skill_id, name, description, xp_cost, effect_type, effect_params, max_level)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (skill_id, skill_id, "", xp_cost, "xp_multiplier", json.dumps({"factor": 1.10}), max_level),
    )
    db.commit()


def _give_xp(db, xp: int) -> None:
    award_category_xp(db, "player_default", Category.WORK, xp)


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    bootstrap_defaults(conn)
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    _seed_skill(db)
    return TestClient(create_app(db=db))


# ── GET /skills returns level / max_level ─────────────────────────────────────

def test_get_skills_includes_level_fields(client, db):
    # Unlock the skill first
    _give_xp(db, 200)
    client.post("/skills/test_skill/unlock")
    r = client.get("/skills")
    assert r.status_code == 200
    skill = next(s for s in r.json() if s["skill_id"] == "test_skill")
    assert skill["level"] == 1
    assert skill["max_level"] == 3


def test_get_skills_locked_level_is_zero(client):
    r = client.get("/skills")
    skill = next(s for s in r.json() if s["skill_id"] == "test_skill")
    assert skill["level"] == 0


# ── POST /skills/{id}/upgrade ─────────────────────────────────────────────────

def test_upgrade_requires_unlock_first(client, db):
    _give_xp(db, 500)
    r = client.post("/skills/test_skill/upgrade")
    assert r.status_code == 409
    assert "not yet unlocked" in r.json()["detail"].lower()


def test_upgrade_succeeds_and_returns_new_level(client, db):
    _give_xp(db, 5000)
    client.post("/skills/test_skill/unlock")      # costs 100 XP
    r = client.post("/skills/test_skill/upgrade")  # costs 100 × 2^1 = 200 XP
    assert r.status_code == 200
    data = r.json()
    assert data["new_level"] == 2
    assert data["xp_spent"] == 200


def test_upgrade_cost_doubles_each_tier(client, db):
    _give_xp(db, 10000)
    client.post("/skills/test_skill/unlock")      # Lv.1, costs 100
    client.post("/skills/test_skill/upgrade")      # Lv.2, costs 200
    r = client.post("/skills/test_skill/upgrade")  # Lv.3, costs 400
    assert r.status_code == 200
    assert r.json()["new_level"] == 3
    assert r.json()["xp_spent"] == 400


def test_upgrade_blocked_at_max_level(client, db):
    _give_xp(db, 10000)
    client.post("/skills/test_skill/unlock")
    client.post("/skills/test_skill/upgrade")
    client.post("/skills/test_skill/upgrade")  # now at max level 3
    r = client.post("/skills/test_skill/upgrade")
    assert r.status_code == 409
    assert "max level" in r.json()["detail"].lower()


def test_upgrade_blocked_insufficient_xp(client, db):
    _give_xp(db, 100)  # enough for unlock but not upgrade
    client.post("/skills/test_skill/unlock")  # spends 100 XP, leaves 0
    r = client.post("/skills/test_skill/upgrade")
    assert r.status_code == 402


def test_upgrade_404_unknown_skill(client):
    r = client.post("/skills/nonexistent/upgrade")
    assert r.status_code == 404


# ── Effect scaling ────────────────────────────────────────────────────────────

def test_skill_effects_scale_with_level(db):
    bootstrap_defaults(db)
    _seed_skill(db, skill_id="scale_skill", xp_cost=100, max_level=3)
    # Unlock at Lv.1
    db.execute(
        "INSERT INTO player_skills (player_id, skill_id, unlocked_at, level)"
        " VALUES ('player_default', 'scale_skill', '2024-01-01', 1)"
    )
    db.commit()
    effs_lv1 = load_skill_effects(db, "player_default")
    factor_lv1 = effs_lv1[0].params["factor"]

    # Upgrade to Lv.2
    db.execute(
        "UPDATE player_skills SET level=2 WHERE player_id='player_default' AND skill_id='scale_skill'"
    )
    db.commit()
    effs_lv2 = load_skill_effects(db, "player_default")
    factor_lv2 = effs_lv2[0].params["factor"]

    assert factor_lv2 > factor_lv1  # scaled up


def test_skill_effect_lv1_unchanged(db):
    bootstrap_defaults(db)
    _seed_skill(db, skill_id="s1", xp_cost=100, max_level=3)
    db.execute(
        "INSERT INTO player_skills (player_id, skill_id, unlocked_at, level)"
        " VALUES ('player_default', 's1', '2024-01-01', 1)"
    )
    db.commit()
    effs = load_skill_effects(db, "player_default")
    # Lv.1 scale = 1 + 0.5*(1-1) = 1.0 → factor unchanged
    assert abs(effs[0].params["factor"] - 1.10) < 0.001
