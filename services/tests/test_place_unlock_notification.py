"""Tests for place_unlock notification enrichment with description and condition."""
import json
import sqlite3
import pytest

from services.storage.db import init_db, bootstrap_defaults
from services.reward_ledger.ledger import insert_place_unlock_notification


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    bootstrap_defaults(conn)
    yield conn
    conn.close()


def _get_place_unlock_payload(db, place_id: str) -> dict | None:
    row = db.execute(
        "SELECT payload FROM pending_notifications"
        " WHERE event_type='place_unlock' AND json_extract(payload, '$.place_id') = ?",
        (place_id,),
    ).fetchone()
    if row is None:
        return None
    return json.loads(row["payload"])


def test_payload_contains_place_name(db):
    insert_place_unlock_notification(db, "player_default", "workshop", "Workshop")
    db.commit()
    payload = _get_place_unlock_payload(db, "workshop")
    assert payload is not None
    assert payload["place_name"] == "Workshop"


def test_payload_contains_description(db):
    insert_place_unlock_notification(
        db, "player_default", "arcade", "Arcade",
        description="A fun gaming space",
    )
    db.commit()
    payload = _get_place_unlock_payload(db, "arcade")
    assert payload["description"] == "A fun gaming space"


def test_payload_contains_condition(db):
    insert_place_unlock_notification(
        db, "player_default", "observatory", "Observatory",
        condition="Reached level 8",
    )
    db.commit()
    payload = _get_place_unlock_payload(db, "observatory")
    assert payload["condition"] == "Reached level 8"


def test_payload_description_defaults_to_empty(db):
    insert_place_unlock_notification(db, "player_default", "lab", "Lab")
    db.commit()
    payload = _get_place_unlock_payload(db, "lab")
    assert payload["description"] == ""


def test_payload_condition_defaults_to_empty(db):
    insert_place_unlock_notification(db, "player_default", "lab2", "Lab 2")
    db.commit()
    payload = _get_place_unlock_payload(db, "lab2")
    assert payload["condition"] == ""


def test_all_fields_present_together(db):
    insert_place_unlock_notification(
        db, "player_default", "hub", "Hub",
        description="Central location",
        condition="Reached level 5",
    )
    db.commit()
    payload = _get_place_unlock_payload(db, "hub")
    assert payload["place_id"] == "hub"
    assert payload["place_name"] == "Hub"
    assert payload["description"] == "Central location"
    assert payload["condition"] == "Reached level 5"
