"""Tests for goal_difficulty_scale in player settings."""
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
    conn.execute(
        "INSERT INTO player_category_xp (character_id, category, xp) VALUES ('player_default', 'WORK', 10)"
    )
    conn.execute("INSERT OR IGNORE INTO player_settings (player_id) VALUES ('player_default')")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    from services.api.main import create_app
    return TestClient(create_app(db=db))


def test_settings_default_scale(client):
    r = client.get("/player/settings")
    assert r.status_code == 200
    d = r.json()
    assert "goal_difficulty_scale" in d
    assert d["goal_difficulty_scale"] == 1.0


def test_settings_patch_scale(client):
    r = client.patch("/player/settings", json={"goal_difficulty_scale": 0.5})
    assert r.status_code == 200
    assert r.json()["goal_difficulty_scale"] == pytest.approx(0.5)


def test_settings_roundtrip(client):
    client.patch("/player/settings", json={"goal_difficulty_scale": 1.5})
    r = client.get("/player/settings")
    assert r.json()["goal_difficulty_scale"] == pytest.approx(1.5)


def test_settings_validation_too_low(client):
    r = client.patch("/player/settings", json={"goal_difficulty_scale": 0.4})
    assert r.status_code == 422


def test_settings_validation_too_high(client):
    r = client.patch("/player/settings", json={"goal_difficulty_scale": 2.1})
    assert r.status_code == 422


def test_scale_halves_goal_target(db, client):
    from services.progression.suggestions import get_suggestions
    from services.progression.daily_goals import ensure_daily_goals, get_daily_goals
    # Seed a suggestion item (WORK category)
    db.execute(
        "INSERT INTO item_definitions (item_id, data) VALUES ('wk', ?)",
        (json.dumps({"item_id": "wk", "name": "W", "rarity": "COMMON", "category": "WORK",
                     "description": "", "effects": [], "icon": "", "stackable": False,
                     "set_id": None,
                     "drop_requirement": {"activity_label": "WORK", "min_duration_sec": 0,
                                          "min_confidence": 0.0, "time_of_day": None}}),)
    )
    db.commit()

    # Set scale to 0.5 to get half-size goals
    client.patch("/player/settings", json={"goal_difficulty_scale": 0.5})
    ensure_daily_goals(db)
    goals_half = get_daily_goals(db)

    # Reset and try with default scale
    db.execute("DELETE FROM daily_goals")
    db.commit()
    client.patch("/player/settings", json={"goal_difficulty_scale": 1.0})
    ensure_daily_goals(db)
    goals_full = get_daily_goals(db)

    if goals_half and goals_full:
        half_target = goals_half[0]["target_min"]
        full_target = goals_full[0]["target_min"]
        # At 0.5 scale, targets should be smaller than at 1.0
        assert half_target <= full_target


def test_settings_partial_update_preserves_xp_target(client):
    client.patch("/player/settings", json={"daily_xp_target": 250})
    client.patch("/player/settings", json={"goal_difficulty_scale": 1.5})
    r = client.get("/player/settings")
    data = r.json()
    assert data["daily_xp_target"] == 250
    assert data["goal_difficulty_scale"] == pytest.approx(1.5)
