import sqlite3
import pytest
from services.storage.db import init_db
from services.models.enums import Category
from services.progression.config import XP_PER_LEVEL, EVOLUTION_STAGES, XP_PER_MINUTE
from services.progression.xp import (
    compute_level, compute_evolution_stage, award_category_xp, get_total_xp,
)


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()


def test_compute_level_at_zero_xp():
    assert compute_level(0) == 1


def test_compute_level_advances():
    level_2_xp = XP_PER_LEVEL[1]
    assert compute_level(level_2_xp) == 2
    assert compute_level(level_2_xp - 1) == 1


def test_compute_evolution_stage_hatchling():
    assert compute_evolution_stage(1) == 0
    assert compute_evolution_stage(5) == 0


def test_compute_evolution_stage_growing():
    assert compute_evolution_stage(6) == 1
    assert compute_evolution_stage(15) == 1


def test_compute_evolution_stage_mature():
    assert compute_evolution_stage(16) == 2
    assert compute_evolution_stage(30) == 2


def test_compute_evolution_stage_legendary():
    assert compute_evolution_stage(31) == 3


def test_award_category_xp_inserts_row(db):
    award_category_xp(db, character_id="p1", category=Category.WORK, xp=50)
    row = db.execute(
        "SELECT xp FROM player_category_xp WHERE character_id=? AND category=?",
        ("p1", "WORK"),
    ).fetchone()
    assert row["xp"] == 50


def test_award_category_xp_accumulates(db):
    award_category_xp(db, character_id="p1", category=Category.WORK, xp=50)
    award_category_xp(db, character_id="p1", category=Category.WORK, xp=30)
    row = db.execute(
        "SELECT xp FROM player_category_xp WHERE character_id=? AND category=?",
        ("p1", "WORK"),
    ).fetchone()
    assert row["xp"] == 80


def test_get_total_xp(db):
    award_category_xp(db, character_id="p1", category=Category.WORK, xp=200)
    award_category_xp(db, character_id="p1", category=Category.GAME, xp=100)
    assert get_total_xp(db, "p1") == 300
