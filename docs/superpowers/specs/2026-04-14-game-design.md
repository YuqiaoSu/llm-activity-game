# LLM Activity Game — Full Product Design

**Date:** 2026-04-14
**Status:** Approved

---

## 1. Product Vision

A companion-based game that turns real, classified activity from `llm-activity-tracker` into progression, item rewards, and an evolving game world. The player's daily behaviour — work, gaming, exploration, social activity, sleep — directly feeds a companion character, an item economy, and a set of places they inhabit.

**Core pillars:**
- Companion with stats and a visual form that grows from real activity
- Item economy with rarity tiers, per-category pools, and typed extensible effects
- Universal Place abstraction that home, dungeon, map zones, and future systems all extend
- Per-category XP that mirrors the player's real activity balance
- Extensibility as a first-class constraint — new systems plug in without touching the core

**MVP scope:** sync agent, drop engine, item/rarity system, reward ledger, character model, Place abstraction, per-category XP. No Godot client, home UI, dungeon logic, or MCP server in the first build.

---

## 2. Architecture

**Approach:** Godot + Python services (Approach A).

```
llm-activity-tracker  ──HTTP──►  Game Services (Python)  ──HTTP──►  Godot Engine
      tracker.db                       game.db                     (thin client)
                                          │
                                    MCP Server (deferred)
                                    (AI agents connect here)
```

### Layer responsibilities

| Layer | Owns | Never does |
|---|---|---|
| `llm-activity-tracker` | Capture, archival, classification, `tracker.db` | Game logic |
| Game Services (Python) | Sync, drop engine, rewards, progression, places | Write to `tracker.db` |
| Godot Engine | Render, input, UI scenes | Business logic, direct DB access |
| MCP Server *(deferred)* | AI-readable/writable game interface | Bypass Game Services for writes |

### Communication
- Game Services polls `GET /v1/chunks?after_cursor=<id>&limit=50` from tracker
- Godot calls Game Services on `localhost:8765` to pull state and post events
- Godot polls `pending_notifications` table for reward animations
- MCP server reads `game.db` directly (read-only); writes go through Game Services

---

## 3. Item & Rarity System

### 3.1 Rarity tiers

| Tier | Default drop weight |
|---|---|
| COMMON | ~60% |
| UNCOMMON | ~25% |
| RARE | ~10% |
| EPIC | ~4% |
| LEGENDARY | ~1% |

Weights are configurable per-place via `PlaceItemPool.drop_weight_mods`. No hardcoded values.

### 3.2 Item categories

`WORK · GAME · VIDEO · SOCIAL · EXPLORE · SLEEP · SPECIAL`

Category is the item's **identity and theme**. It is independent of the drop requirement.

`SPECIAL` items are eligible at every place regardless of `PlaceItemPool.allowed_categories`. They represent cross-category, event, or seasonal items that are never locked to one place type.

### 3.3 Data model

```python
class ItemDefinition:
    item_id:          str               # unique slug e.g. "focus_crystal_rare"
    name:             str
    category:         Category          # item identity — WORK | GAME | ... | SPECIAL
    rarity:           Rarity
    drop_requirement: DropRequirement   # eligibility rule, independent of category
    effects:          list[Effect]      # typed plug-ins, interpreted by target systems
    icon:             str
    description:      str               # flavour text
    stackable:        bool

class DropRequirement:
    activity_label:   str | None        # WORK | GAME | ... | None = any label
    min_duration_sec: int               # minimum chunk duration to be eligible
    min_confidence:   float             # classifier confidence threshold
    time_of_day:      str | None        # "morning" | "night" | None = any
    extra:            dict              # future conditions: streak_active, season, event flag

class Effect:
    effect_type: str    # "stat_buff" | "home_unlock" | "dungeon_mod" | "companion_skin" | ...
    target:      str    # which system handles this effect
    params:      dict   # arbitrary payload interpreted by the target system

class InventoryItem:
    instance_id:  str
    item_id:      str           # → ItemDefinition
    acquired_at:  datetime
    source_chunk: str           # chunk_id that triggered the drop
    equipped:     bool
    placed_in:    str | None    # PlaceSlot.slot_id if placed, None if in bag
```

**Extensibility:** new effect types are registered strings. When a new system activates (home, dungeon), it registers its effect types and starts handling them. Items seeded with those effect types in MVP inventory begin working automatically — no migration needed.

---

## 4. Character Model

Every character in the game — companion, future party members, dungeon enemies — shares one model.

```python
class Character:
    # Identity
    character_id:   str
    name:           str
    character_type: CharacterType   # COMPANION | NPC | ENEMY | BOSS

    # Stats
    level:          int
    xp:             int             # reflects total_xp from PlayerProfile
    hp_max:         int
    hp_current:     int
    attack:         int
    defense:        int
    luck:           int             # influences drop rates
    stat_mods:      dict            # temporary buffs/debuffs from equipped items

    # Visual
    visual:         CharacterVisual

    # Equipment
    equipped_items: list[str]       # InventoryItem.instance_ids

class CharacterVisual:
    base_sprite:      str
    evolution_stage:  int           # drives which sprite set Godot loads
    skin:             str | None    # cosmetic override from companion_skin effect
    accessories:      list[str]     # layered cosmetics from equipped items
    anim_state:       str           # "idle" | "happy" | "tired" | "battle" | ...
```

**Stat mutation rule:** base stats never change. Equipped items write into `stat_mods` only. On unequip, their contribution is removed.

### Evolution stages

| Stage | Name | Level range |
|---|---|---|
| 0 | Hatchling | 1–5 |
| 1 | Growing | 6–15 |
| 2 | Mature | 16–30 |
| 3+ | Legendary form | 31+ |

Thresholds are config values, not hardcoded.

---

## 5. Per-Category XP & Player Profile

```python
class PlayerProfile:
    character_id:    str
    # Overall (derived)
    total_xp:        int                    # always == sum(category_xp.values())
    level:           int                    # derived from total_xp
    evolution_stage: int                    # derived from level
    # Per-category
    category_xp:     dict[Category, int]    # {WORK: 1240, GAME: 380, VIDEO: 90, ...}
    # Visual / equipment
    visual:          CharacterVisual
    equipped_items:  list[str]
```

### XP gain sources

| Source | XP pool targeted |
|---|---|
| Tracker chunk synced | `category_xp[chunk.label]` |
| Place activity (when `place.category` is set) | `category_xp[place.category]` |
| Item drop received | `category_xp[item.category]` |
| Quest / streak milestone | configured per-quest |

`total_xp` is always the sum of all category rows and is never stored redundantly — it is computed on read or kept consistent via a trigger.

### game.db table

```sql
CREATE TABLE player_category_xp (
    character_id TEXT NOT NULL,
    category     TEXT NOT NULL,
    xp           INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (character_id, category)
);
```

---

## 6. Sync Agent & Drop Engine

### 6.1 Poll triggers

| Trigger | Rate limited? |
|---|---|
| Automatic (configurable interval, default 60s) | No |
| User triggered ("Check rewards" in Godot UI → `POST /sync/poll-now`) | Yes — per-player cooldown |
| MCP triggered (`trigger_sync_poll` tool) | Yes — same cooldown as user |

All three sources invoke the same `SyncAgent.poll()` entry point.

### 6.2 Pipeline

```
SyncAgent.poll()
    │
    ▼
1. Fetch chunks     GET /v1/chunks?after_cursor=<last_id>&limit=50
    │               cursor persisted in sync_state table
    ▼
2. Filter           confidence ≥ threshold
                    duration ≥ min_duration
                    label is known
                    chunk not already processed
    │
    ▼
3. Roll strategy    strategy.compute(chunk, player_state) → int (number of rolls)
    │               swappable: Session | Time | Daily | LuckBonus | Composite
    ▼
4. Lottery          eligible = [items where drop_requirement.matches(chunk)
                                AND item in place.item_pool (if place context)]
                    winner = weighted_random(eligible, by rarity + drop_weight_mods)
    │
    ▼
5. Reward ledger    INSERT OR IGNORE key (chunk_id, roll_n)
                    → write to inventory + award category XP
                    → write to pending_notifications for Godot
```

### 6.3 Roll strategy interface

```python
class RollStrategy:  # abstract
    def compute(self, chunk: Chunk, player: PlayerState) -> int: ...

# Built-in implementations
SessionStrategy    # 1 roll per qualifying chunk
TimeStrategy       # 1 roll per N minutes of activity
DailyStrategy      # batch rolls at day rollover
LuckBonusStrategy  # extra rolls proportional to companion luck stat
CompositeStrategy  # combines any of the above
```

### 6.4 Idempotency

`reward_ledger` has `PRIMARY KEY (chunk_id, roll_n)`. The pipeline is safe to replay at any point — duplicate inserts are silently ignored.

### 6.5 Rate limit (manual triggers)

```python
if now - last_manual_poll_at < manual_poll_cooldown_sec:
    return PollResult.ON_COOLDOWN   # Godot shows "Ready in Xs"
else:
    run_poll()
    update last_manual_poll_at
```

---

## 7. Universal Place Object

A `Place` is the abstract base for any location — home room, dungeon floor, map zone, or future system. No subclassing; `place_type` and `metadata` carry what is specific to each system.

```python
class Place:
    # Identity
    place_id:         str
    name:             str
    place_type:       str               # "home" | "dungeon" | "map_zone" | any future string
    description:      str
    icon:             str | None

    # Category link (optional)
    category:         Category | None   # drives XP pool + default item pool filter

    # Item pool
    item_pool:        PlaceItemPool

    # State machine
    state:            PlaceState        # LOCKED | UNLOCKED | ACTIVE | COMPLETED
    unlock_condition: Condition | None
    metadata:         dict              # type-specific, interpreted by owning system

    # Slots
    slots:            list[PlaceSlot]

    # Connections
    connected_to:     list[str]         # place_ids (graph edges)
    parent_place:     str | None        # hierarchy (room inside home, floor inside dungeon)

    # Active effects
    active_effects:   list[Effect]      # aggregated from all filled slots, rebuilt on change

class PlaceItemPool:
    allowed_categories:  list[Category] | None    # None = all categories
    allowed_rarities:    list[Rarity] | None       # None = all rarities
    explicit_items:      list[str] | None          # specific item_ids, overrides category filter
    drop_weight_mods:    dict[str, float]           # per-rarity weight overrides for this place

class PlaceSlot:
    slot_id:      str
    slot_type:    SlotType              # ITEM | CHARACTER | ANY
    accepts:      list[str] | None      # filter by category, character_type, etc. None = no filter
    occupant_id:  str | None            # instance_id or character_id currently placed
    metadata:     dict                  # position, visual anchor, constraints

class Condition:
    condition_type: str     # "item_in_inventory" | "player_level" | "place_completed" | ...
    params:         dict    # open dict — extensible without schema change
```

### How `place.category` links three things

| `place.category` set to... | XP effect | Item pool default |
|---|---|---|
| `WORK` | `category_xp[WORK] += xp` on activity here | WORK items eligible (SPECIAL always included) |
| `EXPLORE` | `category_xp[EXPLORE] += xp` | EXPLORE items eligible (SPECIAL always included) |
| `None` | No targeted XP | All categories eligible |

**Rule:** `SPECIAL` items bypass `allowed_categories` and are always included in every place's pool. `item_pool.explicit_items` can still exclude them if needed.

`item_pool` fields override the category default explicitly.

### game.db tables

```sql
CREATE TABLE places (
    place_id          TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    place_type        TEXT NOT NULL,
    category          TEXT,               -- nullable
    state             TEXT NOT NULL DEFAULT 'LOCKED',
    unlock_condition  TEXT,               -- JSON
    item_pool         TEXT NOT NULL,      -- JSON
    connected_to      TEXT NOT NULL DEFAULT '[]',  -- JSON array
    parent_place      TEXT,
    metadata          TEXT NOT NULL DEFAULT '{}'   -- JSON
);

CREATE TABLE place_slots (
    slot_id      TEXT PRIMARY KEY,
    place_id     TEXT NOT NULL REFERENCES places(place_id),
    slot_type    TEXT NOT NULL,
    accepts      TEXT,          -- JSON array or NULL
    occupant_id  TEXT,
    metadata     TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE place_active_effects (
    effect_id      TEXT PRIMARY KEY,
    place_id       TEXT NOT NULL REFERENCES places(place_id),
    source_slot_id TEXT NOT NULL REFERENCES place_slots(slot_id),
    effect_type    TEXT NOT NULL,
    params         TEXT NOT NULL DEFAULT '{}',
    applied_at     TEXT NOT NULL
    -- rebuilt fully whenever a slot's occupant changes
);
```

### Extensibility pattern

Adding a new system (e.g. map, crafting bench):

1. Register new `effect_type` strings in the effect registry
2. Add system-specific tables to `game.db` (core tables never change)
3. Add Godot scenes that call Game Services for state

Items with `home_unlock`, `dungeon_mod`, etc. effects can already exist in MVP inventory. When the system activates, those effects start working — no item data migration.

---

## 8. game.db — Full Table Summary

| Table | Purpose |
|---|---|
| `sync_state` | Tracker cursor, last sync timestamp |
| `reward_ledger` | Idempotent drop log keyed on `(chunk_id, roll_n)` |
| `inventory` | Player's held items |
| `pending_notifications` | Reward events waiting for Godot to acknowledge |
| `player_profile` | Character identity, visual, equipment |
| `player_category_xp` | Per-category XP `(character_id, category)` |
| `places` | Universal place definitions |
| `place_slots` | Slots within each place |
| `place_active_effects` | Materialised active effects from filled slots |

---

## 9. MVP Build Scope

### Included

- `sync_agent` — polls tracker, advances cursor, rate-limits manual triggers
- `drop_engine` — configurable `RollStrategy`, weighted lottery, `DropRequirement` matching
- Item/rarity system — `ItemDefinition`, `DropRequirement`, `Effect` registry, `InventoryItem`
- `reward_ledger` — idempotent, keyed on `(chunk_id, roll_n)`
- `pending_notifications` — Godot polling table
- Character model — `Character`, `CharacterVisual`, `stat_mods` layer
- `PlayerProfile` + `player_category_xp` — per-category XP, derived total/level
- Universal `Place` model — three tables, seed one `place_type="home"` place with empty slots

### Deferred

| System | Notes |
|---|---|
| Godot client | All UI scenes |
| Home system | Place tables ready; home service + Godot scenes deferred |
| Dungeon system | Character stats ready; dungeon service + Godot scenes deferred |
| MCP server | Architecture designed; implementation deferred |
| Quest engine | Designed for via `DropRequirement.extra`; not built |
| Steam integration | Deferred until Godot client exists |

---

## 10. Repository Layout (target)

```
llm-activity-game/
  services/
    sync_agent/         # polls tracker, drives drop pipeline
    drop_engine/        # RollStrategy, lottery, DropRequirement
    reward_ledger/      # idempotent write layer
    progression/        # XP, level, evolution stage
    place_service/      # Place CRUD, slot management, effect aggregation
  storage/
    schema.sql          # game.db DDL
    migrations/
  contracts/            # tracker chunk payload schema, sync cursor rules
  game-client/          # Godot project (deferred)
  assets/
  steam/                # deferred
  docs/
```
