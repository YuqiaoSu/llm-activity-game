from __future__ import annotations
import json
import sqlite3
from services.models.enums import PlaceState, SlotType
from services.models.place import Place, PlaceItemPool, PlaceSlot, Condition


def _row_to_place(conn: sqlite3.Connection, row: sqlite3.Row) -> Place:
    slots = conn.execute(
        "SELECT * FROM place_slots WHERE place_id=? ORDER BY slot_id",
        (row["place_id"],),
    ).fetchall()
    return Place(
        place_id=row["place_id"],
        name=row["name"],
        place_type=row["place_type"],
        description=row["description"] or "",
        icon=row["icon"],
        category=row["category"],
        state=row["state"],
        unlock_condition=json.loads(row["unlock_condition"]) if row["unlock_condition"] else None,
        item_pool=PlaceItemPool(**json.loads(row["item_pool"])),
        connected_to=json.loads(row["connected_to"]),
        parent_place=row["parent_place"],
        metadata=json.loads(row["metadata"]),
        slots=[
            PlaceSlot(
                slot_id=s["slot_id"],
                place_id=s["place_id"],
                slot_type=s["slot_type"],
                accepts=json.loads(s["accepts"]) if s["accepts"] else None,
                occupant_id=s["occupant_id"],
                metadata=json.loads(s["metadata"]),
            )
            for s in slots
        ],
    )


def save_place(conn: sqlite3.Connection, place: Place) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO places
            (place_id, name, place_type, description, icon, category, state,
             unlock_condition, item_pool, connected_to, parent_place, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            place.place_id, place.name, place.place_type, place.description,
            place.icon,
            str(place.category.value) if place.category else None,
            str(place.state.value),
            place.unlock_condition.model_dump_json() if place.unlock_condition else None,
            place.item_pool.model_dump_json(),
            json.dumps(place.connected_to),
            place.parent_place,
            json.dumps(place.metadata),
        ),
    )
    for slot in place.slots:
        conn.execute(
            """
            INSERT OR REPLACE INTO place_slots
                (slot_id, place_id, slot_type, accepts, occupant_id, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                slot.slot_id, slot.place_id, str(slot.slot_type.value),
                json.dumps(slot.accepts) if slot.accepts is not None else None,
                slot.occupant_id,
                json.dumps(slot.metadata),
            ),
        )
    conn.commit()


def get_place(conn: sqlite3.Connection, place_id: str) -> Place | None:
    row = conn.execute("SELECT * FROM places WHERE place_id=?", (place_id,)).fetchone()
    return _row_to_place(conn, row) if row else None


def list_places(conn: sqlite3.Connection) -> list[Place]:
    rows = conn.execute("SELECT * FROM places ORDER BY place_id").fetchall()
    return [_row_to_place(conn, row) for row in rows]


def set_slot_occupant(
    conn: sqlite3.Connection,
    slot_id: str,
    occupant_id: str | None,
) -> None:
    conn.execute(
        "UPDATE place_slots SET occupant_id=? WHERE slot_id=?",
        (occupant_id, slot_id),
    )
    conn.commit()


def check_unlock_condition(
    conn: sqlite3.Connection,
    place: Place,
    player_level: int,
) -> bool:
    """Evaluate the place's unlock_condition. None = always unlocked."""
    cond = place.unlock_condition
    if cond is None:
        return True
    if cond.condition_type == "player_level":
        return player_level >= cond.params.get("min_level", 1)
    return False  # unknown condition types default to locked
