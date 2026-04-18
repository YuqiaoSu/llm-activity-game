"""Streak milestone rewards — guaranteed drops at multiples of MILESTONE_INTERVAL days.

Called from agent.poll() after update_streak(). Idempotent: the reward_ledger
UNIQUE(chunk_id, roll_n) constraint ensures each milestone fires at most once.

Milestone rarity priority:
  1. EPIC
  2. LEGENDARY
  3. RARE (fallback if no EPIC/LEGENDARY items exist in the catalogue)
  4. Any rarity (last resort)
"""
from __future__ import annotations

import logging
import random
import sqlite3

from services.reward_ledger.ledger import record_drop, insert_streak_milestone_notification
from services.models.item import ItemDefinition

logger = logging.getLogger(__name__)

MILESTONE_INTERVAL = 7          # every N days
_PREFERRED_RARITIES = ["EPIC", "LEGENDARY", "RARE"]


def _milestone_chunk_id(streak: int) -> str:
    return f"streak_milestone_{streak}"


def _already_granted(conn: sqlite3.Connection, streak: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM reward_ledger WHERE chunk_id=? AND roll_n=0",
        (_milestone_chunk_id(streak),),
    ).fetchone()
    return row is not None


def _load_items_by_rarity(conn: sqlite3.Connection, rarity: str) -> list[ItemDefinition]:
    rows = conn.execute(
        """
        SELECT data FROM item_definitions
        WHERE json_extract(data, '$.rarity') = ?
        """,
        (rarity,),
    ).fetchall()
    items: list[ItemDefinition] = []
    for row in rows:
        try:
            items.append(ItemDefinition.model_validate_json(row["data"]))
        except Exception:
            pass
    return items


def check_streak_milestone_drop(
    conn: sqlite3.Connection,
    character_id: str,
    current_streak: int,
) -> bool:
    """Grant a guaranteed high-rarity drop if current_streak is a milestone.

    Returns True if a drop was granted, False otherwise.
    """
    if current_streak <= 0 or current_streak % MILESTONE_INTERVAL != 0:
        return False

    if _already_granted(conn, current_streak):
        logger.debug("Milestone %d already granted for %s", current_streak, character_id)
        return False

    # Pick the best available rarity
    winner: ItemDefinition | None = None
    for rarity in _PREFERRED_RARITIES:
        candidates = _load_items_by_rarity(conn, rarity)
        if candidates:
            winner = random.choice(candidates)
            break

    if winner is None:
        # Fall back to any item
        rows = conn.execute("SELECT data FROM item_definitions LIMIT 20").fetchall()
        all_items: list[ItemDefinition] = []
        for row in rows:
            try:
                all_items.append(ItemDefinition.model_validate_json(row["data"]))
            except Exception:
                pass
        if all_items:
            winner = random.choice(all_items)

    if winner is None:
        logger.warning("Streak milestone %d: no items in catalogue — skipping drop", current_streak)
        return False

    record_drop(
        conn,
        chunk_id=_milestone_chunk_id(current_streak),
        roll_n=0,
        item=winner,
        character_id=character_id,
    )
    insert_streak_milestone_notification(conn, character_id, current_streak)
    logger.info(
        "Streak milestone %d: granted %s (%s) to %s",
        current_streak, winner.item_id, winner.rarity.value, character_id,
    )
    return True
