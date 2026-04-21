# LLM Activity Game

A FastAPI backend for a gamification layer built on top of
[llm-activity-tracker](https://github.com/YuqiaoSu/llm-activity-tracker).
Real-world activity (coding, studying, gaming) is tracked by the tracker,
synced here, and converted into XP, item drops, place unlocks, and progression.

See [docs/gamification-overview.md](docs/gamification-overview.md) for the
full design narrative.

---

## Architecture Overview

```
llm-activity-tracker  ──HTTP──▶  SyncAgent.poll()
                                       │
                          ┌────────────┼────────────┐
                          ▼            ▼             ▼
                     XP / Level    Item Drops    Streak / Goals
                          │            │             │
                          └────────────▼─────────────┘
                               SQLite (game.db)
                                       │
                               FastAPI REST API
                                       │
                            Godot game client (game-client/)
```

The tracker remains the source of truth for activity capture and classification.
This repo owns only game-facing state: inventory, places, progression, and rewards.

---

## Quick Start

### 1 — Install dependencies

```bash
pip install -r requirements-dev.txt   # includes pytest + httpx
```

### 2 — Start the API

```bash
uvicorn services.api.main:app --reload --port 8000
```

Swagger docs are available at `http://localhost:8000/docs`.

### 3 — Seed development data (optional)

```bash
python -m services.seeds.seed_items
python -m services.seeds.seed_places
```

---

## Requirements

- Python 3.11+
- `fastapi`, `uvicorn[standard]`, `httpx`, `pydantic`
- A running `llm-activity-tracker` instance reachable at the configured tracker URL

See `pyproject.toml` for pinned versions.

---

## Project Layout

```
services/
  api/
    main.py              # FastAPI app factory + background poll loop
    routers/
      inventory.py       # Item lifecycle: sell, fuse, craft, upgrade, tags
      places.py          # Place mechanics: slots, visits, donations, upgrades
      player.py          # Profile, XP, luck, titles, mood, streaks, settings
      challenges.py      # Weekly challenges and daily bonus rotation
      achievements.py    # Achievement unlock tracking
      leaderboard.py     # XP and streak rankings
      recap.py           # Daily / weekly activity recaps
      catalogue.py       # Item catalog browser
      notifications.py   # Pending notification queue
      history.py         # Activity history with filters
      stats.py           # Player statistics aggregates
      trade.py           # Player-to-player item trading
      collection.py      # Collection completion tracking
      goals.py           # Daily goal management
      suggestions.py     # Goal and activity suggestions
      events.py          # Timed challenge events
      feed.py            # Activity feed
      craft.py           # Crafting recipes
      skills.py          # Skill upgrades
      sync.py            # Manual poll trigger endpoint
  models/
    enums.py             # Category, Rarity, CharacterType, SlotType, PlaceState
    player.py            # PlayerProfile
    item.py              # ItemDefinition, DropRequirement
    place.py             # Place, PlaceItemPool, PlaceSlot
    character.py         # CharacterVisual
  progression/           # XP, levels, streaks, goals, achievements, decay, mood
  place_service/         # Place lookup, upgrade, and effect computation
  drop_engine/           # Rarity-weighted item lottery
  reward_ledger/         # Drop recording and notification insertion
  sync_agent/            # Tracker polling, cursor management, rate limiting
  storage/
    db.py                # Database init, schema application, migrations
  notifications/         # Desktop notification integration
  contracts/
    chunk.py             # Chunk data contract (shared with tracker)
  seeds/                 # Development seed scripts
game-client/             # Godot client (scenes, scripts, assets)
contracts/               # Tracker-to-game integration contracts
docs/                    # Architecture and design documentation
assets/                  # Game art and brand assets
```

---

## Testing

```bash
python -m pytest services/tests/
```

The test suite uses an in-memory SQLite database and a mock tracker client —
no running tracker or Godot client is required.

---

## API Reference

Interactive docs (Swagger UI) are served at `/docs` when the server is running.
All endpoints accept and return JSON.  Common status codes:

| Code | Meaning |
|---|---|
| 200 / 201 | Success |
| 400 | Bad request (invalid input) |
| 402 | Insufficient XP |
| 404 | Resource not found |
| 409 | Conflict (item locked, already at max, etc.) |

---

## License

Private / unreleased.
