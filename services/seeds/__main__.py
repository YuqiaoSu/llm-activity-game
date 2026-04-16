"""
Run: python -m services.seeds [--db path/to/game.db]
Seeds item definitions, places, default player profile, and sync_state.
"""
import argparse
import json
from services.storage.db import get_db
from services.place_service.service import save_place
from services.seeds.items import SEED_ITEMS
from services.seeds.places import SEED_PLACES
from services.seeds.achievements import SEED_ACHIEVEMENTS
from services.seeds.weekly_challenges import SEED_WEEKLY_CHALLENGES
from services.seeds.events import get_seed_events
from services.seeds.trade import seed_trade_offers


def seed(db_path: str = "game.db") -> None:
    conn = get_db(db_path)

    print(f"Seeding into {db_path}...")

    # Items
    for item in SEED_ITEMS:
        conn.execute(
            "INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?, ?)",
            (item.item_id, item.model_dump_json()),
        )
    print(f"  {len(SEED_ITEMS)} item definitions seeded.")

    # Places
    for place in SEED_PLACES:
        save_place(conn, place)
    print(f"  {len(SEED_PLACES)} places seeded.")

    # Achievements
    for ach in SEED_ACHIEVEMENTS:
        conn.execute(
            "INSERT OR IGNORE INTO achievements (achievement_id, name, description, condition_type, threshold) VALUES (?, ?, ?, ?, ?)",
            ach,
        )
    print(f"  {len(SEED_ACHIEVEMENTS)} achievement definitions seeded.")

    # Weekly challenges
    for ch in SEED_WEEKLY_CHALLENGES:
        conn.execute(
            "INSERT OR IGNORE INTO weekly_challenges (challenge_id, name, description, category, metric, threshold) VALUES (?, ?, ?, ?, ?, ?)",
            ch,
        )
    print(f"  {len(SEED_WEEKLY_CHALLENGES)} weekly challenge definitions seeded.")

    # Challenge events
    events = get_seed_events()
    for ev in events:
        conn.execute(
            "INSERT OR IGNORE INTO challenge_events "
            "(event_id, label, category, multiplier, starts_at, ends_at) VALUES (?,?,?,?,?,?)",
            ev,
        )
    print(f"  {len(events)} challenge events seeded.")

    # Default player profile
    default_visual = json.dumps({
        "base_sprite": "companion_hatchling.png",
        "evolution_stage": 0, "skin": None, "accessories": [], "anim_state": "idle",
    })
    conn.execute(
        """
        INSERT OR IGNORE INTO player_profile (character_id, name, visual)
        VALUES ('player_default', 'Lumi', ?)
        """,
        (default_visual,),
    )
    print("  Default player profile seeded.")

    # Sync state
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")
    print("  Sync state initialized.")

    # Trade offers
    n_trades = seed_trade_offers(conn)
    print(f"  {n_trades} trade offers seeded.")

    conn.commit()
    conn.close()
    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed game.db")
    parser.add_argument("--db", default="game.db", help="Path to game.db")
    args = parser.parse_args()
    seed(args.db)
