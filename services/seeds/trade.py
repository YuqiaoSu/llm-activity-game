"""Seed NPC trade offer definitions."""
from __future__ import annotations

import sqlite3


_OFFERS = [
    {
        "offer_id":    "trade_common_to_uncommon",
        "trader_name": "Merchant Arlo",
        "label":       "3× Common → 1 Uncommon",
        "from_rarity": "COMMON",
        "from_qty":    3,
        "from_category": None,
        "to_rarity":   "UNCOMMON",
        "to_qty":      1,
        "to_category": None,
    },
    {
        "offer_id":    "trade_uncommon_to_rare",
        "trader_name": "Merchant Arlo",
        "label":       "3× Uncommon → 1 Rare",
        "from_rarity": "UNCOMMON",
        "from_qty":    3,
        "from_category": None,
        "to_rarity":   "RARE",
        "to_qty":      1,
        "to_category": None,
    },
    {
        "offer_id":    "trade_rare_to_epic",
        "trader_name": "Sage Mirella",
        "label":       "4× Rare → 1 Epic",
        "from_rarity": "RARE",
        "from_qty":    4,
        "from_category": None,
        "to_rarity":   "EPIC",
        "to_qty":      1,
        "to_category": None,
    },
    {
        "offer_id":    "trade_focus_common_to_rare",
        "trader_name": "Scholar Vex",
        "label":       "5× Common FOCUS → 1 Rare FOCUS",
        "from_rarity": "COMMON",
        "from_qty":    5,
        "from_category": "focus",
        "to_rarity":   "RARE",
        "to_qty":      1,
        "to_category": "focus",
    },
    {
        "offer_id":    "trade_epic_to_legendary",
        "trader_name": "Sage Mirella",
        "label":       "5× Epic → 1 Legendary",
        "from_rarity": "EPIC",
        "from_qty":    5,
        "from_category": None,
        "to_rarity":   "LEGENDARY",
        "to_qty":      1,
        "to_category": None,
    },
]


def seed_trade_offers(conn: sqlite3.Connection) -> int:
    """Insert trade offers if not already present. Returns count inserted."""
    inserted = 0
    for o in _OFFERS:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO trade_offers
                (offer_id, trader_name, label, from_rarity, from_qty, from_category, to_rarity, to_qty, to_category)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (o["offer_id"], o["trader_name"], o["label"],
             o["from_rarity"], o["from_qty"], o["from_category"],
             o["to_rarity"], o["to_qty"], o["to_category"]),
        )
        inserted += cur.rowcount
    conn.commit()
    return inserted
