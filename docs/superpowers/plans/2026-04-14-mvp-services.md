# LLM Activity Game — MVP Services Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Python game-services layer — sync agent, drop engine, item/rarity system, reward ledger, character model, player profile, place abstraction, per-category XP, and a FastAPI HTTP server — so Godot can later plug in as a thin client.

**Architecture:** Pure Python package under `services/`; SQLite (`game.db`) as the single store; FastAPI on `localhost:8765`; `httpx` polls the tracker's `/v1/chunks` endpoint; all domain models are Pydantic v2 `BaseModel`; no ORM (plain `sqlite3`).

**Tech Stack:** Python 3.11+, Pydantic v2, FastAPI, Uvicorn, httpx, pytest, uv (package manager), SQLite (stdlib).

---

## File Map

```
llm-activity-game/
  pyproject.toml
  pytest.ini
  services/
    __init__.py
    models/
      __init__.py
      enums.py          # Category, Rarity, CharacterType, SlotType, PlaceState
      item.py           # Effect, DropRequirement, ItemDefinition, InventoryItem
      character.py      # CharacterVisual, Character
      player.py         # PlayerProfile
      place.py          # Condition, PlaceItemPool, PlaceSlot, Place
    storage/
      __init__.py
      db.py             # get_db(), init_db()
    contracts/
      __init__.py
      chunk.py          # Chunk, SyncState
    progression/
      __init__.py
      config.py         # XP_PER_LEVEL list, EVOLUTION_STAGES, XP_PER_MINUTE_OF_ACTIVITY
      xp.py             # award_category_xp(), compute_level(), compute_evolution_stage(), get_profile()
    drop_engine/
      __init__.py
      lottery.py        # eligible_items(), weighted_draw()
      strategies.py     # RollStrategy ABC + SessionStrategy, TimeStrategy, LuckBonusStrategy, CompositeStrategy
    reward_ledger/
      __init__.py
      ledger.py         # record_drop() — idempotent insert, XP award, notification push
    place_service/
      __init__.py
      service.py        # get_place(), list_places(), set_slot_occupant(), check_unlock_condition()
      effects.py        # rebuild_active_effects()
    sync_agent/
      __init__.py
      rate_limiter.py   # RateLimiter (manual-poll cooldown)
      tracker_client.py # TrackerClient.fetch_chunks()
      agent.py          # SyncAgent.poll()
    api/
      __init__.py
      main.py           # FastAPI app, lifespan, router mounts
      routers/
        __init__.py
        sync.py         # POST /sync/poll-now, GET /sync/status
        inventory.py    # GET /inventory
        player.py       # GET /player/profile
        places.py       # GET /places, GET /places/{place_id}
        notifications.py # GET /notifications/pending, POST /notifications/{id}/ack
    seeds/
      __init__.py
      items.py          # 10 seed ItemDefinitions across categories + rarities
      places.py         # seed home Place (UNLOCKED, empty slots)
      __main__.py       # python -m services.seeds
    tests/
      __init__.py
      conftest.py
      test_enums.py
      test_item_models.py
      test_character_models.py
      test_player_models.py
      test_place_models.py
      test_drop_requirements.py
      test_strategies.py
      test_lottery.py
      test_progression.py
      test_reward_ledger.py
      test_place_service.py
      test_sync_agent.py
      test_api.py
  storage/
    schema.sql          # full game.db DDL
    migrations/         # empty for now
```

**Dependency order (strictly followed):** enums → schema/db → contracts → item models → character models → player models → place models → progression → drop_engine → reward_ledger → place_service → sync_agent → API → seeds.

---

## Task 1: Project Bootstrap

**Files:**
- Create: `pyproject.toml`
- Create: `pytest.ini`
- Create: `services/__init__.py` (and all sub-package `__init__.py` stubs)

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "llm-activity-game-services"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "httpx>=0.27.0",
    "pydantic>=2.9.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.0",
    "httpx>=0.27.0",
]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["services/tests"]
```

- [ ] **Step 2: Create `pytest.ini`**

```ini
[pytest]
pythonpath = .
testpaths = services/tests
```

- [ ] **Step 3: Create all `__init__.py` stubs**

```bash
# Run from llm-activity-game/
mkdir -p services/models services/storage services/contracts \
         services/progression services/drop_engine services/reward_ledger \
         services/place_service services/sync_agent \
         services/api/routers services/seeds services/tests \
         storage/migrations

touch services/__init__.py \
      services/models/__init__.py \
      services/storage/__init__.py \
      services/contracts/__init__.py \
      services/progression/__init__.py \
      services/drop_engine/__init__.py \
      services/reward_ledger/__init__.py \
      services/place_service/__init__.py \
      services/sync_agent/__init__.py \
      services/api/__init__.py \
      services/api/routers/__init__.py \
      services/seeds/__init__.py \
      services/tests/__init__.py
```

- [ ] **Step 4: Install dependencies**

```bash
uv pip install -e ".[dev]"
```

Expected: All packages installed without errors.

- [ ] **Step 5: Create `services/tests/conftest.py` stub**

```python
import sqlite3
import pytest
from services.storage.db import init_db


@pytest.fixture
def db():
    """In-memory SQLite db, fully initialized with schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()
```

- [ ] **Step 6: Verify pytest collects zero tests without error**

```bash
pytest --collect-only
```

Expected: `no tests ran` (0 errors).

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml pytest.ini services/ storage/
git commit -m "chore: bootstrap Python project structure"
```

---

## Task 2: Core Enums

**Files:**
- Create: `services/models/enums.py`
- Create: `services/tests/test_enums.py`

- [ ] **Step 1: Write failing test**

```python
# services/tests/test_enums.py
from services.models.enums import Category, Rarity, CharacterType, SlotType, PlaceState


def test_category_values():
    assert set(Category) == {
        Category.WORK, Category.GAME, Category.VIDEO,
        Category.SOCIAL, Category.EXPLORE, Category.SLEEP, Category.SPECIAL,
    }


def test_rarity_values():
    assert list(Rarity) == [
        Rarity.COMMON, Rarity.UNCOMMON, Rarity.RARE, Rarity.EPIC, Rarity.LEGENDARY,
    ]


def test_enums_are_strings():
    assert Category.WORK == "WORK"
    assert Rarity.COMMON == "COMMON"


def test_place_state_values():
    assert set(PlaceState) == {
        PlaceState.LOCKED, PlaceState.UNLOCKED, PlaceState.ACTIVE, PlaceState.COMPLETED,
    }
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest services/tests/test_enums.py -v
```

Expected: `ModuleNotFoundError: No module named 'services.models.enums'`

- [ ] **Step 3: Implement `services/models/enums.py`**

```python
from enum import Enum


class Category(str, Enum):
    WORK = "WORK"
    GAME = "GAME"
    VIDEO = "VIDEO"
    SOCIAL = "SOCIAL"
    EXPLORE = "EXPLORE"
    SLEEP = "SLEEP"
    SPECIAL = "SPECIAL"


class Rarity(str, Enum):
    COMMON = "COMMON"
    UNCOMMON = "UNCOMMON"
    RARE = "RARE"
    EPIC = "EPIC"
    LEGENDARY = "LEGENDARY"


class CharacterType(str, Enum):
    COMPANION = "COMPANION"
    NPC = "NPC"
    ENEMY = "ENEMY"
    BOSS = "BOSS"


class SlotType(str, Enum):
    ITEM = "ITEM"
    CHARACTER = "CHARACTER"
    ANY = "ANY"


class PlaceState(str, Enum):
    LOCKED = "LOCKED"
    UNLOCKED = "UNLOCKED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest services/tests/test_enums.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add services/models/enums.py services/tests/test_enums.py
git commit -m "feat: add core enums (Category, Rarity, CharacterType, SlotType, PlaceState)"
```

---

## Task 3: Database Schema & Connection

**Files:**
- Create: `storage/schema.sql`
- Create: `services/storage/db.py`

- [ ] **Step 1: Create `storage/schema.sql`**

```sql
-- sync_state: one row per player, tracks cursor into tracker
CREATE TABLE IF NOT EXISTS sync_state (
    player_id            TEXT PRIMARY KEY DEFAULT 'default',
    last_cursor          TEXT,                -- last chunk_id processed
    last_sync_at         TEXT,                -- ISO-8601 datetime
    last_manual_poll_at  TEXT                 -- ISO-8601 datetime, rate-limit anchor
);

-- item_definitions: catalogue of all item templates (loaded from seeds)
CREATE TABLE IF NOT EXISTS item_definitions (
    item_id  TEXT PRIMARY KEY,
    data     TEXT NOT NULL               -- JSON: full ItemDefinition
);

-- inventory: items owned by a player character
CREATE TABLE IF NOT EXISTS inventory (
    instance_id   TEXT PRIMARY KEY,
    character_id  TEXT NOT NULL,
    item_id       TEXT NOT NULL,
    acquired_at   TEXT NOT NULL,           -- ISO-8601
    source_chunk  TEXT NOT NULL,           -- chunk_id that triggered the drop
    equipped      INTEGER NOT NULL DEFAULT 0,
    placed_in     TEXT                     -- PlaceSlot.slot_id or NULL
);

-- reward_ledger: idempotent drop log; (chunk_id, roll_n) prevents re-award on replay
CREATE TABLE IF NOT EXISTS reward_ledger (
    ledger_id     TEXT PRIMARY KEY,        -- UUID
    chunk_id      TEXT NOT NULL,
    roll_n        INTEGER NOT NULL,
    item_id       TEXT NOT NULL,
    character_id  TEXT NOT NULL,
    awarded_at    TEXT NOT NULL,
    UNIQUE (chunk_id, roll_n)
);

-- pending_notifications: reward events waiting for Godot to acknowledge
CREATE TABLE IF NOT EXISTS pending_notifications (
    notification_id  TEXT PRIMARY KEY,     -- UUID
    character_id     TEXT NOT NULL,
    event_type       TEXT NOT NULL,        -- "item_drop" | "xp_gain" | "level_up"
    payload          TEXT NOT NULL,        -- JSON
    created_at       TEXT NOT NULL,
    acknowledged     INTEGER NOT NULL DEFAULT 0
);

-- player_profile: character identity, visual, equipment
CREATE TABLE IF NOT EXISTS player_profile (
    character_id   TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    character_type TEXT NOT NULL DEFAULT 'COMPANION',
    level          INTEGER NOT NULL DEFAULT 1,
    hp_max         INTEGER NOT NULL DEFAULT 100,
    hp_current     INTEGER NOT NULL DEFAULT 100,
    attack         INTEGER NOT NULL DEFAULT 10,
    defense        INTEGER NOT NULL DEFAULT 10,
    luck           INTEGER NOT NULL DEFAULT 5,
    stat_mods      TEXT NOT NULL DEFAULT '{}',   -- JSON
    visual         TEXT NOT NULL,                -- JSON CharacterVisual
    equipped_items TEXT NOT NULL DEFAULT '[]'    -- JSON list[str] instance_ids
);

-- player_category_xp: per-category XP; total_xp is always SUM of all rows for a character
CREATE TABLE IF NOT EXISTS player_category_xp (
    character_id  TEXT NOT NULL,
    category      TEXT NOT NULL,
    xp            INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (character_id, category)
);

-- places: universal place definitions
CREATE TABLE IF NOT EXISTS places (
    place_id          TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    place_type        TEXT NOT NULL,
    description       TEXT NOT NULL DEFAULT '',
    icon              TEXT,
    category          TEXT,                           -- nullable Category
    state             TEXT NOT NULL DEFAULT 'LOCKED',
    unlock_condition  TEXT,                           -- JSON Condition or NULL
    item_pool         TEXT NOT NULL,                  -- JSON PlaceItemPool
    connected_to      TEXT NOT NULL DEFAULT '[]',     -- JSON list[str] place_ids
    parent_place      TEXT,
    metadata          TEXT NOT NULL DEFAULT '{}'
);

-- place_slots: slots within a place
CREATE TABLE IF NOT EXISTS place_slots (
    slot_id      TEXT PRIMARY KEY,
    place_id     TEXT NOT NULL REFERENCES places(place_id),
    slot_type    TEXT NOT NULL,
    accepts      TEXT,                               -- JSON list[str] or NULL
    occupant_id  TEXT,
    metadata     TEXT NOT NULL DEFAULT '{}'
);

-- place_active_effects: materialised effects from filled slots; rebuilt on slot change
CREATE TABLE IF NOT EXISTS place_active_effects (
    effect_id       TEXT PRIMARY KEY,
    place_id        TEXT NOT NULL REFERENCES places(place_id),
    source_slot_id  TEXT NOT NULL REFERENCES place_slots(slot_id),
    effect_type     TEXT NOT NULL,
    params          TEXT NOT NULL DEFAULT '{}',      -- JSON
    applied_at      TEXT NOT NULL
);
```

- [ ] **Step 2: Write failing test for `db.py`**

```python
# services/tests/test_db.py  (create new file)
import sqlite3
from services.storage.db import init_db, get_db


def test_init_db_creates_all_tables():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = {row[0] for row in cur.fetchall()}
    expected = {
        "sync_state", "item_definitions", "inventory", "reward_ledger",
        "pending_notifications", "player_profile", "player_category_xp",
        "places", "place_slots", "place_active_effects",
    }
    assert expected == tables
    conn.close()


def test_get_db_returns_connection(tmp_path):
    db_path = tmp_path / "test.db"
    conn = get_db(str(db_path))
    assert conn is not None
    conn.close()
```

- [ ] **Step 3: Run — expect FAIL**

```bash
pytest services/tests/test_db.py -v
```

Expected: `ModuleNotFoundError: No module named 'services.storage.db'`

- [ ] **Step 4: Implement `services/storage/db.py`**

```python
import sqlite3
from pathlib import Path

_SCHEMA_PATH = Path(__file__).parent.parent.parent / "storage" / "schema.sql"


def init_db(conn: sqlite3.Connection) -> None:
    """Execute schema.sql against the given connection."""
    schema = _SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema)
    conn.commit()


def get_db(path: str = "game.db") -> sqlite3.Connection:
    """Open (or create) the SQLite database at `path`, initialize schema, return connection."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    init_db(conn)
    return conn
```

- [ ] **Step 5: Run — expect PASS**

```bash
pytest services/tests/test_db.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Update `conftest.py` to use the real `init_db`**

The stub in Task 1 already calls `init_db(conn)` — no change needed; tests now resolve correctly.

- [ ] **Step 7: Commit**

```bash
git add storage/schema.sql services/storage/db.py services/tests/test_db.py
git commit -m "feat: add game.db schema and connection helper"
```

---

## Task 4: Tracker Contract (Chunk & SyncState)

**Files:**
- Create: `services/contracts/chunk.py`
- Create: `services/tests/test_contracts.py`

- [ ] **Step 1: Write failing test**

```python
# services/tests/test_contracts.py
from datetime import datetime, timezone
from services.contracts.chunk import Chunk, SyncState


def test_chunk_requires_fields():
    c = Chunk(
        chunk_id="c_001",
        label="WORK",
        duration_sec=1800,
        confidence=0.92,
        started_at=datetime(2026, 4, 14, 9, 0, tzinfo=timezone.utc),
    )
    assert c.chunk_id == "c_001"
    assert c.label == "WORK"
    assert c.time_of_day is None


def test_chunk_with_time_of_day():
    c = Chunk(
        chunk_id="c_002",
        label="SLEEP",
        duration_sec=28800,
        confidence=0.99,
        started_at=datetime(2026, 4, 14, 23, 0, tzinfo=timezone.utc),
        time_of_day="night",
    )
    assert c.time_of_day == "night"


def test_sync_state_defaults():
    s = SyncState()
    assert s.last_cursor is None
    assert s.last_sync_at is None
    assert s.last_manual_poll_at is None
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest services/tests/test_contracts.py -v
```

Expected: `ModuleNotFoundError: No module named 'services.contracts.chunk'`

- [ ] **Step 3: Implement `services/contracts/chunk.py`**

```python
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel


class Chunk(BaseModel):
    """A classified activity window from llm-activity-tracker /v1/chunks."""
    chunk_id: str
    label: str                  # matches Category string values (WORK, GAME, …)
    duration_sec: int
    confidence: float           # 0.0–1.0
    started_at: datetime
    time_of_day: str | None = None  # "morning" | "afternoon" | "evening" | "night"


class SyncState(BaseModel):
    """Persisted cursor into the tracker stream."""
    last_cursor: str | None = None
    last_sync_at: datetime | None = None
    last_manual_poll_at: datetime | None = None
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest services/tests/test_contracts.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add services/contracts/chunk.py services/tests/test_contracts.py
git commit -m "feat: add tracker contract types (Chunk, SyncState)"
```

---

## Task 5: Item Domain Models

**Files:**
- Create: `services/models/item.py`
- Create: `services/tests/test_item_models.py`

- [ ] **Step 1: Write failing test**

```python
# services/tests/test_item_models.py
from datetime import datetime, timezone
from services.models.enums import Category, Rarity
from services.models.item import Effect, DropRequirement, ItemDefinition, InventoryItem
from services.contracts.chunk import Chunk


def _chunk(**kw) -> Chunk:
    defaults = dict(
        chunk_id="c_001", label="WORK", duration_sec=1800,
        confidence=0.92, started_at=datetime(2026, 4, 14, 9, 0, tzinfo=timezone.utc),
    )
    return Chunk(**{**defaults, **kw})


def test_effect_creation():
    e = Effect(effect_type="stat_buff", target="companion", params={"luck": 2})
    assert e.effect_type == "stat_buff"
    assert e.params["luck"] == 2


def test_drop_requirement_defaults():
    req = DropRequirement()
    assert req.activity_label is None
    assert req.min_duration_sec == 0
    assert req.min_confidence == 0.0


def test_drop_requirement_matches_any_chunk():
    req = DropRequirement()
    assert req.matches(_chunk()) is True


def test_drop_requirement_label_filter():
    req = DropRequirement(activity_label="WORK")
    assert req.matches(_chunk(label="WORK")) is True
    assert req.matches(_chunk(label="GAME")) is False


def test_drop_requirement_min_duration():
    req = DropRequirement(min_duration_sec=3600)
    assert req.matches(_chunk(duration_sec=3600)) is True
    assert req.matches(_chunk(duration_sec=3599)) is False


def test_drop_requirement_min_confidence():
    req = DropRequirement(min_confidence=0.95)
    assert req.matches(_chunk(confidence=0.95)) is True
    assert req.matches(_chunk(confidence=0.94)) is False


def test_drop_requirement_time_of_day():
    req = DropRequirement(time_of_day="morning")
    assert req.matches(_chunk(time_of_day="morning")) is True
    assert req.matches(_chunk(time_of_day="night")) is False
    assert req.matches(_chunk(time_of_day=None)) is False


def test_item_definition_creation():
    item = ItemDefinition(
        item_id="focus_crystal_rare",
        name="Focus Crystal",
        category=Category.WORK,
        rarity=Rarity.RARE,
        drop_requirement=DropRequirement(activity_label="WORK", min_duration_sec=1800),
        effects=[Effect(effect_type="stat_buff", target="companion", params={"attack": 3})],
        icon="focus_crystal.png",
        description="Formed from deep concentration.",
        stackable=False,
    )
    assert item.rarity == Rarity.RARE
    assert len(item.effects) == 1


def test_inventory_item_creation():
    inv = InventoryItem(
        instance_id="inv_001",
        item_id="focus_crystal_rare",
        acquired_at=datetime(2026, 4, 14, tzinfo=timezone.utc),
        source_chunk="c_001",
    )
    assert inv.equipped is False
    assert inv.placed_in is None
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest services/tests/test_item_models.py -v
```

Expected: `ModuleNotFoundError: No module named 'services.models.item'`

- [ ] **Step 3: Implement `services/models/item.py`**

```python
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel
from services.models.enums import Category, Rarity


class Effect(BaseModel):
    """A typed, extensible payload interpreted by whichever system owns `target`."""
    effect_type: str
    target: str
    params: dict = {}


class DropRequirement(BaseModel):
    """Eligibility rule evaluated against a Chunk. All conditions must pass."""
    activity_label: str | None = None       # None = any label
    min_duration_sec: int = 0
    min_confidence: float = 0.0
    time_of_day: str | None = None          # None = any time
    extra: dict = {}                        # future: streak_active, season, event

    def matches(self, chunk: "Chunk") -> bool:  # type: ignore[name-defined]
        if self.activity_label is not None and self.activity_label != chunk.label:
            return False
        if chunk.duration_sec < self.min_duration_sec:
            return False
        if chunk.confidence < self.min_confidence:
            return False
        if self.time_of_day is not None and self.time_of_day != chunk.time_of_day:
            return False
        return True


class ItemDefinition(BaseModel):
    item_id: str
    name: str
    category: Category
    rarity: Rarity
    drop_requirement: DropRequirement
    effects: list[Effect] = []
    icon: str
    description: str
    stackable: bool = False


class InventoryItem(BaseModel):
    instance_id: str
    item_id: str
    acquired_at: datetime
    source_chunk: str
    equipped: bool = False
    placed_in: str | None = None      # PlaceSlot.slot_id or None
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest services/tests/test_item_models.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add services/models/item.py services/tests/test_item_models.py
git commit -m "feat: add item domain models with DropRequirement.matches()"
```

---

## Task 6: Character & Player Models

**Files:**
- Create: `services/models/character.py`
- Create: `services/models/player.py`
- Create: `services/tests/test_character_models.py`
- Create: `services/tests/test_player_models.py`

- [ ] **Step 1: Write failing tests**

```python
# services/tests/test_character_models.py
from services.models.enums import CharacterType
from services.models.character import CharacterVisual, Character


def test_character_visual_defaults():
    v = CharacterVisual(base_sprite="companion_base.png")
    assert v.evolution_stage == 0
    assert v.skin is None
    assert v.accessories == []
    assert v.anim_state == "idle"


def test_character_creation():
    c = Character(
        character_id="player_001",
        name="Lumi",
        character_type=CharacterType.COMPANION,
        visual=CharacterVisual(base_sprite="lumi_base.png"),
    )
    assert c.level == 1
    assert c.luck == 5
    assert c.stat_mods == {}
    assert c.equipped_items == []


def test_character_stat_mods_are_separate_from_base():
    c = Character(
        character_id="p", name="X", character_type=CharacterType.COMPANION,
        attack=10, luck=5,
        stat_mods={"attack": 3},
        visual=CharacterVisual(base_sprite="x.png"),
    )
    # Base stats unchanged; stat_mods is the overlay
    assert c.attack == 10
    assert c.stat_mods["attack"] == 3
```

```python
# services/tests/test_player_models.py
from services.models.enums import Category
from services.models.character import CharacterVisual
from services.models.player import PlayerProfile


def test_player_profile_defaults():
    p = PlayerProfile(
        character_id="player_001",
        visual=CharacterVisual(base_sprite="lumi.png"),
    )
    assert p.total_xp == 0
    assert p.level == 1
    assert p.evolution_stage == 0
    assert p.category_xp == {}
    assert p.equipped_items == []


def test_player_profile_total_xp_is_sum_of_categories():
    p = PlayerProfile(
        character_id="player_001",
        visual=CharacterVisual(base_sprite="lumi.png"),
        category_xp={Category.WORK: 500, Category.GAME: 300, Category.SLEEP: 200},
        total_xp=1000,
    )
    assert p.total_xp == sum(p.category_xp.values())
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest services/tests/test_character_models.py services/tests/test_player_models.py -v
```

Expected: `ModuleNotFoundError: No module named 'services.models.character'`

- [ ] **Step 3: Implement `services/models/character.py`**

```python
from __future__ import annotations
from pydantic import BaseModel
from services.models.enums import CharacterType


class CharacterVisual(BaseModel):
    base_sprite: str
    evolution_stage: int = 0
    skin: str | None = None
    accessories: list[str] = []
    anim_state: str = "idle"


class Character(BaseModel):
    character_id: str
    name: str
    character_type: CharacterType
    level: int = 1
    xp: int = 0
    hp_max: int = 100
    hp_current: int = 100
    attack: int = 10
    defense: int = 10
    luck: int = 5
    stat_mods: dict = {}          # overlay only — base stats above never change
    visual: CharacterVisual
    equipped_items: list[str] = []   # InventoryItem.instance_ids
```

- [ ] **Step 4: Implement `services/models/player.py`**

```python
from __future__ import annotations
from pydantic import BaseModel, model_validator
from services.models.enums import Category
from services.models.character import CharacterVisual


class PlayerProfile(BaseModel):
    character_id: str
    total_xp: int = 0            # always == sum(category_xp.values())
    level: int = 1
    evolution_stage: int = 0
    category_xp: dict[Category, int] = {}
    visual: CharacterVisual
    equipped_items: list[str] = []

    @model_validator(mode="after")
    def _sync_total_xp(self) -> "PlayerProfile":
        if self.category_xp:
            object.__setattr__(self, "total_xp", sum(self.category_xp.values()))
        return self
```

- [ ] **Step 5: Run — expect PASS**

```bash
pytest services/tests/test_character_models.py services/tests/test_player_models.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add services/models/character.py services/models/player.py \
        services/tests/test_character_models.py services/tests/test_player_models.py
git commit -m "feat: add Character and PlayerProfile domain models"
```

---

## Task 7: Place Domain Models

**Files:**
- Create: `services/models/place.py`
- Create: `services/tests/test_place_models.py`

- [ ] **Step 1: Write failing test**

```python
# services/tests/test_place_models.py
from services.models.enums import Category, Rarity, SlotType, PlaceState
from services.models.item import Effect
from services.models.place import Condition, PlaceItemPool, PlaceSlot, Place


def test_place_item_pool_defaults():
    pool = PlaceItemPool()
    assert pool.allowed_categories is None
    assert pool.allowed_rarities is None
    assert pool.explicit_items is None
    assert pool.drop_weight_mods == {}


def test_place_slot_creation():
    slot = PlaceSlot(slot_id="s_001", place_id="home_001", slot_type=SlotType.ITEM)
    assert slot.occupant_id is None
    assert slot.accepts is None


def test_place_creation_minimal():
    place = Place(
        place_id="home_001",
        name="Study",
        place_type="home",
        item_pool=PlaceItemPool(allowed_categories=[Category.WORK]),
    )
    assert place.state == PlaceState.LOCKED
    assert place.category is None
    assert place.slots == []
    assert place.connected_to == []
    assert place.active_effects == []


def test_place_with_category_and_slots():
    place = Place(
        place_id="home_001",
        name="Study",
        place_type="home",
        category=Category.WORK,
        state=PlaceState.UNLOCKED,
        item_pool=PlaceItemPool(allowed_categories=[Category.WORK]),
        slots=[
            PlaceSlot(slot_id="s_1", place_id="home_001", slot_type=SlotType.ITEM),
            PlaceSlot(slot_id="s_2", place_id="home_001", slot_type=SlotType.CHARACTER),
        ],
    )
    assert len(place.slots) == 2
    assert place.category == Category.WORK


def test_condition_open_params():
    cond = Condition(condition_type="player_level", params={"min_level": 5})
    assert cond.params["min_level"] == 5
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest services/tests/test_place_models.py -v
```

- [ ] **Step 3: Implement `services/models/place.py`**

```python
from __future__ import annotations
from pydantic import BaseModel
from services.models.enums import Category, Rarity, SlotType, PlaceState
from services.models.item import Effect


class Condition(BaseModel):
    condition_type: str
    params: dict = {}


class PlaceItemPool(BaseModel):
    allowed_categories: list[Category] | None = None    # None = all
    allowed_rarities: list[Rarity] | None = None         # None = all
    explicit_items: list[str] | None = None              # overrides category filter
    drop_weight_mods: dict[str, float] = {}              # rarity string → multiplier


class PlaceSlot(BaseModel):
    slot_id: str
    place_id: str
    slot_type: SlotType
    accepts: list[str] | None = None    # category/character_type filter; None = no filter
    occupant_id: str | None = None
    metadata: dict = {}


class Place(BaseModel):
    place_id: str
    name: str
    place_type: str
    description: str = ""
    icon: str | None = None
    category: Category | None = None
    item_pool: PlaceItemPool
    state: PlaceState = PlaceState.LOCKED
    unlock_condition: Condition | None = None
    metadata: dict = {}
    slots: list[PlaceSlot] = []
    connected_to: list[str] = []
    parent_place: str | None = None
    active_effects: list[Effect] = []   # rebuilt whenever a slot occupant changes
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest services/tests/test_place_models.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add services/models/place.py services/tests/test_place_models.py
git commit -m "feat: add Place domain models"
```

---

## Task 8: Progression Service

**Files:**
- Create: `services/progression/config.py`
- Create: `services/progression/xp.py`
- Create: `services/tests/test_progression.py`

- [ ] **Step 1: Write failing tests**

```python
# services/tests/test_progression.py
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
    level_2_xp = XP_PER_LEVEL[1]   # XP_PER_LEVEL[i] = min XP to reach level i+1
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
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest services/tests/test_progression.py -v
```

- [ ] **Step 3: Implement `services/progression/config.py`**

```python
# XP_PER_LEVEL[i] = cumulative XP required to reach level (i+1)
# Level 1 = 0 XP (index 0 unused but kept for clarity)
XP_PER_LEVEL: list[int] = [
    0,     # level 1 (start)
    100,   # level 2
    250,   # level 3
    500,   # level 4
    900,   # level 5
    1_400, # level 6
    2_000, # level 7
    2_750, # level 8
    3_600, # level 9
    4_600, # level 10
    # Each additional level costs ~1000 more XP than the previous gap
]

# EVOLUTION_STAGES: {stage: (min_level, max_level)}
EVOLUTION_STAGES: dict[int, tuple[int, int]] = {
    0: (1, 5),    # Hatchling
    1: (6, 15),   # Growing
    2: (16, 30),  # Mature
    3: (31, 999), # Legendary
}

# XP awarded per minute of classified activity in a chunk
XP_PER_MINUTE: int = 1
```

- [ ] **Step 4: Implement `services/progression/xp.py`**

```python
import sqlite3
from services.models.enums import Category
from services.progression.config import XP_PER_LEVEL, EVOLUTION_STAGES, XP_PER_MINUTE
from services.contracts.chunk import Chunk


def compute_level(total_xp: int) -> int:
    """Return the level corresponding to total_xp (1-indexed)."""
    level = 1
    for i, threshold in enumerate(XP_PER_LEVEL):
        if total_xp >= threshold:
            level = i + 1
        else:
            break
    return level


def compute_evolution_stage(level: int) -> int:
    """Return evolution stage for a given level."""
    for stage, (min_lvl, max_lvl) in sorted(EVOLUTION_STAGES.items(), reverse=True):
        if level >= min_lvl:
            return stage
    return 0


def xp_for_chunk(chunk: Chunk) -> int:
    """XP to award for one processed chunk: 1 XP per minute, minimum 1."""
    return max(1, chunk.duration_sec // 60 * XP_PER_MINUTE)


def award_category_xp(
    conn: sqlite3.Connection,
    character_id: str,
    category: Category,
    xp: int,
) -> None:
    """Upsert XP into player_category_xp. Safe to call multiple times."""
    conn.execute(
        """
        INSERT INTO player_category_xp (character_id, category, xp)
        VALUES (?, ?, ?)
        ON CONFLICT (character_id, category) DO UPDATE SET xp = xp + excluded.xp
        """,
        (character_id, str(category.value), xp),
    )
    conn.commit()


def get_total_xp(conn: sqlite3.Connection, character_id: str) -> int:
    """Sum all category XP rows for a character."""
    row = conn.execute(
        "SELECT COALESCE(SUM(xp), 0) as total FROM player_category_xp WHERE character_id=?",
        (character_id,),
    ).fetchone()
    return int(row[0])
```

- [ ] **Step 5: Run — expect PASS**

```bash
pytest services/tests/test_progression.py -v
```

Expected: 9 passed.

- [ ] **Step 6: Commit**

```bash
git add services/progression/ services/tests/test_progression.py
git commit -m "feat: add progression service (XP, level, evolution stage)"
```

---

## Task 9: Drop Engine — Lottery

**Files:**
- Create: `services/drop_engine/lottery.py`
- Create: `services/tests/test_lottery.py`

- [ ] **Step 1: Write failing tests**

```python
# services/tests/test_lottery.py
import random
from datetime import datetime, timezone
from services.models.enums import Category, Rarity
from services.models.item import DropRequirement, ItemDefinition, Effect
from services.models.place import Place, PlaceItemPool
from services.contracts.chunk import Chunk
from services.drop_engine.lottery import eligible_items, weighted_draw

_VISUAL = {"base_sprite": "x.png"}


def _item(item_id, label, rarity, min_dur=0) -> ItemDefinition:
    return ItemDefinition(
        item_id=item_id, name=item_id, category=Category.WORK, rarity=rarity,
        drop_requirement=DropRequirement(activity_label=label, min_duration_sec=min_dur),
        icon="x.png", description="",
    )


def _chunk(label="WORK", duration_sec=1800, confidence=0.9, time_of_day=None) -> Chunk:
    return Chunk(
        chunk_id="c1", label=label, duration_sec=duration_sec,
        confidence=confidence, started_at=datetime(2026, 4, 14, 9, 0, tzinfo=timezone.utc),
        time_of_day=time_of_day,
    )


def _place(categories=None, rarities=None, explicit=None) -> Place:
    return Place(
        place_id="p1", name="Home", place_type="home",
        item_pool=PlaceItemPool(
            allowed_categories=categories,
            allowed_rarities=rarities,
            explicit_items=explicit,
        ),
    )


CATALOGUE = [
    _item("work_common", "WORK", Rarity.COMMON),
    _item("work_rare", "WORK", Rarity.RARE),
    _item("game_common", "GAME", Rarity.COMMON),
    _item("special_epic", None, Rarity.EPIC),   # SPECIAL-category item: label None = any
]


def test_eligible_items_no_place_filter():
    """All matching-requirement items are eligible when place has no category filter."""
    chunk = _chunk("WORK")
    place = _place()  # no filters
    result = eligible_items(CATALOGUE, chunk, place)
    ids = {i.item_id for i in result}
    assert "work_common" in ids
    assert "work_rare" in ids
    # game_common requires GAME label — should not match WORK chunk
    assert "game_common" not in ids


def test_eligible_items_place_category_filter():
    """Place allowed_categories restricts eligible pool; SPECIAL always passes."""
    # Make a SPECIAL-category item in the catalogue
    special_item = ItemDefinition(
        item_id="special_item", name="S", category=Category.SPECIAL,
        rarity=Rarity.EPIC,
        drop_requirement=DropRequirement(),  # matches any chunk
        icon="s.png", description="",
    )
    cat = CATALOGUE + [special_item]
    place = _place(categories=[Category.WORK])
    chunk = _chunk("WORK")
    result = eligible_items(cat, chunk, place)
    ids = {i.item_id for i in result}
    assert "work_common" in ids
    assert "special_item" in ids   # SPECIAL bypasses category filter
    assert "game_common" not in ids


def test_eligible_items_rarity_filter():
    place = _place(rarities=[Rarity.COMMON])
    chunk = _chunk("WORK")
    result = eligible_items(CATALOGUE, chunk, place)
    assert all(i.rarity == Rarity.COMMON for i in result)


def test_weighted_draw_returns_item():
    random.seed(42)
    items = [CATALOGUE[0], CATALOGUE[1]]
    weights = {Rarity.COMMON: 60.0, Rarity.RARE: 10.0}
    result = weighted_draw(items, weights, drop_weight_mods={})
    assert result is not None
    assert result in items


def test_weighted_draw_empty_returns_none():
    assert weighted_draw([], {}, {}) is None
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest services/tests/test_lottery.py -v
```

- [ ] **Step 3: Implement `services/drop_engine/lottery.py`**

```python
from __future__ import annotations
import random
from services.models.enums import Category, Rarity
from services.models.item import ItemDefinition
from services.models.place import Place
from services.contracts.chunk import Chunk

DEFAULT_RARITY_WEIGHTS: dict[Rarity, float] = {
    Rarity.COMMON: 60.0,
    Rarity.UNCOMMON: 25.0,
    Rarity.RARE: 10.0,
    Rarity.EPIC: 4.0,
    Rarity.LEGENDARY: 1.0,
}


def eligible_items(
    catalogue: list[ItemDefinition],
    chunk: Chunk,
    place: Place,
) -> list[ItemDefinition]:
    """
    Return items from `catalogue` that:
    1. Pass their own DropRequirement against `chunk`.
    2. Pass the place's item_pool filters (category/rarity/explicit).
       SPECIAL-category items bypass allowed_categories.
    """
    pool = place.item_pool
    result: list[ItemDefinition] = []

    for item in catalogue:
        # 1. DropRequirement gate
        if not item.drop_requirement.matches(chunk):
            continue

        # 2. Explicit override (if set, only these IDs are eligible)
        if pool.explicit_items is not None:
            if item.item_id not in pool.explicit_items:
                continue

        # 3. Category filter (SPECIAL always passes)
        if pool.allowed_categories is not None and item.category != Category.SPECIAL:
            if item.category not in pool.allowed_categories:
                continue

        # 4. Rarity filter
        if pool.allowed_rarities is not None:
            if item.rarity not in pool.allowed_rarities:
                continue

        result.append(item)

    return result


def weighted_draw(
    items: list[ItemDefinition],
    base_weights: dict[Rarity, float],
    drop_weight_mods: dict[str, float],
) -> ItemDefinition | None:
    """Weighted random draw; `drop_weight_mods` multiplies a rarity's base weight."""
    if not items:
        return None

    weights: list[float] = []
    for item in items:
        base = base_weights.get(item.rarity, 1.0)
        mod = drop_weight_mods.get(str(item.rarity), 1.0)
        weights.append(base * mod)

    return random.choices(items, weights=weights, k=1)[0]
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest services/tests/test_lottery.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add services/drop_engine/lottery.py services/tests/test_lottery.py
git commit -m "feat: add drop engine lottery (eligible_items, weighted_draw)"
```

---

## Task 10: Drop Engine — Roll Strategies

**Files:**
- Create: `services/drop_engine/strategies.py`
- Create: `services/tests/test_strategies.py`

- [ ] **Step 1: Write failing tests**

```python
# services/tests/test_strategies.py
from datetime import datetime, timezone
from services.contracts.chunk import Chunk
from services.drop_engine.strategies import (
    SessionStrategy, TimeStrategy, LuckBonusStrategy, CompositeStrategy,
)


def _chunk(duration_sec=1800) -> Chunk:
    return Chunk(
        chunk_id="c1", label="WORK", duration_sec=duration_sec,
        confidence=0.9, started_at=datetime(2026, 4, 14, 9, 0, tzinfo=timezone.utc),
    )


def test_session_strategy_always_one():
    s = SessionStrategy()
    assert s.compute(_chunk(), luck=5) == 1
    assert s.compute(_chunk(duration_sec=10), luck=5) == 1


def test_time_strategy_one_per_interval():
    s = TimeStrategy(interval_sec=900)   # 1 roll per 15 minutes
    assert s.compute(_chunk(duration_sec=900), luck=0) == 1
    assert s.compute(_chunk(duration_sec=1800), luck=0) == 2
    assert s.compute(_chunk(duration_sec=450), luck=0) == 0


def test_time_strategy_minimum_zero():
    s = TimeStrategy(interval_sec=3600)
    assert s.compute(_chunk(duration_sec=100), luck=0) == 0


def test_luck_bonus_strategy_adds_extra_rolls():
    s = LuckBonusStrategy(luck_per_roll=10)
    # luck=10 → 1 extra roll
    assert s.compute(_chunk(), luck=10) == 1
    # luck=5 → 0 extra rolls
    assert s.compute(_chunk(), luck=5) == 0


def test_composite_strategy_sums():
    s = CompositeStrategy([SessionStrategy(), TimeStrategy(interval_sec=900)])
    # 1 (session) + 2 (1800s / 900s) = 3
    assert s.compute(_chunk(duration_sec=1800), luck=0) == 3


def test_composite_strategy_with_luck():
    s = CompositeStrategy([SessionStrategy(), LuckBonusStrategy(luck_per_roll=5)])
    assert s.compute(_chunk(), luck=10) == 3  # 1 + 2
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest services/tests/test_strategies.py -v
```

- [ ] **Step 3: Implement `services/drop_engine/strategies.py`**

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from services.contracts.chunk import Chunk


class RollStrategy(ABC):
    """Abstract roll strategy. Returns number of lottery rolls for a chunk."""

    @abstractmethod
    def compute(self, chunk: Chunk, luck: int) -> int: ...


class SessionStrategy(RollStrategy):
    """Always 1 roll per qualifying chunk, regardless of duration."""

    def compute(self, chunk: Chunk, luck: int) -> int:
        return 1


class TimeStrategy(RollStrategy):
    """1 roll per `interval_sec` of chunk duration (integer division)."""

    def __init__(self, interval_sec: int = 900) -> None:
        self.interval_sec = interval_sec

    def compute(self, chunk: Chunk, luck: int) -> int:
        return chunk.duration_sec // self.interval_sec


class LuckBonusStrategy(RollStrategy):
    """Extra rolls = luck // luck_per_roll."""

    def __init__(self, luck_per_roll: int = 10) -> None:
        self.luck_per_roll = luck_per_roll

    def compute(self, chunk: Chunk, luck: int) -> int:
        return luck // self.luck_per_roll


class CompositeStrategy(RollStrategy):
    """Sum rolls from multiple strategies."""

    def __init__(self, strategies: list[RollStrategy]) -> None:
        self.strategies = strategies

    def compute(self, chunk: Chunk, luck: int) -> int:
        return sum(s.compute(chunk, luck) for s in self.strategies)
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest services/tests/test_strategies.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add services/drop_engine/strategies.py services/tests/test_strategies.py
git commit -m "feat: add roll strategies (Session, Time, LuckBonus, Composite)"
```

---

## Task 11: Reward Ledger

**Files:**
- Create: `services/reward_ledger/ledger.py`
- Create: `services/tests/test_reward_ledger.py`

- [ ] **Step 1: Write failing tests**

```python
# services/tests/test_reward_ledger.py
import sqlite3
import pytest
from datetime import datetime, timezone
from services.storage.db import init_db
from services.models.enums import Category
from services.models.item import ItemDefinition, DropRequirement
from services.reward_ledger.ledger import record_drop, get_pending_notifications


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()


def _item(item_id="focus_crystal") -> ItemDefinition:
    from services.models.enums import Rarity
    return ItemDefinition(
        item_id=item_id, name="Focus Crystal", category=Category.WORK,
        rarity=Rarity.RARE, drop_requirement=DropRequirement(),
        icon="x.png", description="",
    )


def test_record_drop_inserts_inventory_row(db):
    record_drop(db, chunk_id="c1", roll_n=0, item=_item(), character_id="p1")
    rows = db.execute("SELECT * FROM inventory WHERE character_id='p1'").fetchall()
    assert len(rows) == 1
    assert rows[0]["item_id"] == "focus_crystal"


def test_record_drop_idempotent(db):
    """Replaying the same (chunk_id, roll_n) must not insert a duplicate."""
    record_drop(db, chunk_id="c1", roll_n=0, item=_item(), character_id="p1")
    record_drop(db, chunk_id="c1", roll_n=0, item=_item(), character_id="p1")
    rows = db.execute("SELECT * FROM inventory WHERE character_id='p1'").fetchall()
    assert len(rows) == 1


def test_record_drop_awards_category_xp(db):
    record_drop(db, chunk_id="c1", roll_n=0, item=_item(), character_id="p1")
    row = db.execute(
        "SELECT xp FROM player_category_xp WHERE character_id='p1' AND category='WORK'"
    ).fetchone()
    assert row is not None
    assert row["xp"] > 0


def test_record_drop_creates_notification(db):
    record_drop(db, chunk_id="c1", roll_n=0, item=_item(), character_id="p1")
    notifs = get_pending_notifications(db, character_id="p1")
    assert len(notifs) == 1
    assert notifs[0]["event_type"] == "item_drop"


def test_get_pending_notifications_excludes_acknowledged(db):
    record_drop(db, chunk_id="c1", roll_n=0, item=_item(), character_id="p1")
    notif_id = db.execute(
        "SELECT notification_id FROM pending_notifications WHERE character_id='p1'"
    ).fetchone()["notification_id"]
    db.execute(
        "UPDATE pending_notifications SET acknowledged=1 WHERE notification_id=?",
        (notif_id,),
    )
    db.commit()
    assert get_pending_notifications(db, character_id="p1") == []
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest services/tests/test_reward_ledger.py -v
```

- [ ] **Step 3: Implement `services/reward_ledger/ledger.py`**

```python
from __future__ import annotations
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from services.models.item import ItemDefinition
from services.progression.xp import award_category_xp
from services.models.enums import Category

_XP_PER_DROP = 5   # flat XP bonus for receiving any item


def record_drop(
    conn: sqlite3.Connection,
    chunk_id: str,
    roll_n: int,
    item: ItemDefinition,
    character_id: str,
) -> bool:
    """
    Idempotent drop record. Returns True if the row was newly inserted, False if duplicate.
    On new insert: writes inventory row, awards category XP, queues notification.
    """
    ledger_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    try:
        conn.execute(
            """
            INSERT INTO reward_ledger (ledger_id, chunk_id, roll_n, item_id, character_id, awarded_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (ledger_id, chunk_id, roll_n, item.item_id, character_id, now),
        )
    except sqlite3.IntegrityError:
        conn.rollback()
        return False  # duplicate — silently ignore

    instance_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk)
        VALUES (?, ?, ?, ?, ?)
        """,
        (instance_id, character_id, item.item_id, now, chunk_id),
    )

    # Award XP for the item's category
    award_category_xp(conn, character_id=character_id, category=item.category, xp=_XP_PER_DROP)

    # Queue a notification for Godot
    notification_id = str(uuid.uuid4())
    payload = json.dumps({"item_id": item.item_id, "instance_id": instance_id, "rarity": item.rarity})
    conn.execute(
        """
        INSERT INTO pending_notifications (notification_id, character_id, event_type, payload, created_at)
        VALUES (?, ?, 'item_drop', ?, ?)
        """,
        (notification_id, character_id, payload, now),
    )
    conn.commit()
    return True


def get_pending_notifications(
    conn: sqlite3.Connection,
    character_id: str,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM pending_notifications
        WHERE character_id=? AND acknowledged=0
        ORDER BY created_at ASC
        """,
        (character_id,),
    ).fetchall()
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest services/tests/test_reward_ledger.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add services/reward_ledger/ledger.py services/tests/test_reward_ledger.py
git commit -m "feat: add reward ledger (idempotent drop recording, XP, notifications)"
```

---

## Task 12: Place Service

**Files:**
- Create: `services/place_service/service.py`
- Create: `services/place_service/effects.py`
- Create: `services/tests/test_place_service.py`

- [ ] **Step 1: Write failing tests**

```python
# services/tests/test_place_service.py
import sqlite3
import json
import pytest
from services.storage.db import init_db
from services.models.enums import Category, PlaceState, SlotType
from services.models.place import Place, PlaceItemPool, PlaceSlot, Condition
from services.place_service.service import (
    save_place, get_place, list_places, set_slot_occupant, check_unlock_condition,
)


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()


def _home_place(state=PlaceState.LOCKED) -> Place:
    return Place(
        place_id="home_001",
        name="Study",
        place_type="home",
        category=Category.WORK,
        state=state,
        item_pool=PlaceItemPool(allowed_categories=[Category.WORK]),
        slots=[
            PlaceSlot(slot_id="s_1", place_id="home_001", slot_type=SlotType.ITEM),
        ],
    )


def test_save_and_get_place(db):
    save_place(db, _home_place())
    place = get_place(db, "home_001")
    assert place is not None
    assert place.name == "Study"
    assert place.category == Category.WORK
    assert len(place.slots) == 1


def test_get_nonexistent_place_returns_none(db):
    assert get_place(db, "no_such_place") is None


def test_list_places(db):
    save_place(db, _home_place())
    places = list_places(db)
    assert len(places) == 1
    assert places[0].place_id == "home_001"


def test_set_slot_occupant(db):
    save_place(db, _home_place())
    set_slot_occupant(db, slot_id="s_1", occupant_id="inv_001")
    place = get_place(db, "home_001")
    assert place.slots[0].occupant_id == "inv_001"


def test_set_slot_occupant_clear(db):
    save_place(db, _home_place())
    set_slot_occupant(db, slot_id="s_1", occupant_id="inv_001")
    set_slot_occupant(db, slot_id="s_1", occupant_id=None)
    place = get_place(db, "home_001")
    assert place.slots[0].occupant_id is None


def test_check_unlock_condition_player_level_met(db):
    place = _home_place()
    place = place.model_copy(update={
        "unlock_condition": Condition(condition_type="player_level", params={"min_level": 3})
    })
    save_place(db, place)
    # player at level 5 should unlock
    assert check_unlock_condition(db, place, player_level=5) is True


def test_check_unlock_condition_player_level_not_met(db):
    place = _home_place()
    place = place.model_copy(update={
        "unlock_condition": Condition(condition_type="player_level", params={"min_level": 10})
    })
    save_place(db, place)
    assert check_unlock_condition(db, place, player_level=5) is False


def test_check_unlock_no_condition(db):
    save_place(db, _home_place())
    place = get_place(db, "home_001")
    assert check_unlock_condition(db, place, player_level=1) is True
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest services/tests/test_place_service.py -v
```

- [ ] **Step 3: Implement `services/place_service/service.py`**

```python
from __future__ import annotations
import json
import sqlite3
from services.models.enums import PlaceState
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
    # Upsert slots
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
    # Unknown condition types default to locked (safe fallback)
    return False
```

- [ ] **Step 4: Create `services/place_service/effects.py`**

```python
from __future__ import annotations
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from services.models.item import Effect
from services.models.place import Place, PlaceSlot


def rebuild_active_effects(conn: sqlite3.Connection, place: Place) -> list[Effect]:
    """
    Delete all active effects for `place`, then re-derive them from occupied slots.
    An occupied slot contributes the equipped item's effects (looked up from item_definitions).
    Returns the new list of active effects.
    """
    conn.execute(
        "DELETE FROM place_active_effects WHERE place_id=?", (place.place_id,)
    )

    active: list[Effect] = []
    now = datetime.now(timezone.utc).isoformat()

    for slot in place.slots:
        if slot.occupant_id is None:
            continue
        # Look up the item definition via inventory → item_definitions
        inv_row = conn.execute(
            "SELECT item_id FROM inventory WHERE instance_id=?", (slot.occupant_id,)
        ).fetchone()
        if not inv_row:
            continue
        item_row = conn.execute(
            "SELECT data FROM item_definitions WHERE item_id=?", (inv_row["item_id"],)
        ).fetchone()
        if not item_row:
            continue
        item_data = json.loads(item_row["data"])
        for effect_dict in item_data.get("effects", []):
            effect = Effect(**effect_dict)
            effect_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO place_active_effects
                    (effect_id, place_id, source_slot_id, effect_type, params, applied_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (effect_id, place.place_id, slot.slot_id,
                 effect.effect_type, json.dumps(effect.params), now),
            )
            active.append(effect)

    conn.commit()
    return active
```

- [ ] **Step 5: Run — expect PASS**

```bash
pytest services/tests/test_place_service.py -v
```

Expected: 8 passed.

- [ ] **Step 6: Commit**

```bash
git add services/place_service/ services/tests/test_place_service.py
git commit -m "feat: add place service (CRUD, slot occupant, unlock check, effect rebuild)"
```

---

## Task 13: Sync Agent

**Files:**
- Create: `services/sync_agent/rate_limiter.py`
- Create: `services/sync_agent/tracker_client.py`
- Create: `services/sync_agent/agent.py`
- Create: `services/tests/test_sync_agent.py`

- [ ] **Step 1: Write failing tests**

```python
# services/tests/test_sync_agent.py
import sqlite3
import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from services.storage.db import init_db
from services.sync_agent.rate_limiter import RateLimiter
from services.sync_agent.agent import SyncAgent, PollResult
from services.models.enums import Category, Rarity
from services.models.item import ItemDefinition, DropRequirement
from services.drop_engine.strategies import SessionStrategy
from services.drop_engine.lottery import DEFAULT_RARITY_WEIGHTS


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    # Seed one item definition
    item = ItemDefinition(
        item_id="work_common_001", name="Work Scroll",
        category=Category.WORK, rarity=Rarity.COMMON,
        drop_requirement=DropRequirement(min_confidence=0.5),
        icon="scroll.png", description="",
    )
    conn.execute(
        "INSERT INTO item_definitions (item_id, data) VALUES (?, ?)",
        (item.item_id, item.model_dump_json()),
    )
    # Seed default player profile
    visual = json.dumps({"base_sprite": "lumi.png", "evolution_stage": 0,
                         "skin": None, "accessories": [], "anim_state": "idle"})
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES (?, ?, ?)",
        ("player_default", "Lumi", visual),
    )
    # Seed sync_state row
    conn.execute(
        "INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')"
    )
    conn.commit()
    yield conn
    conn.close()


def test_rate_limiter_allows_first_call():
    rl = RateLimiter(cooldown_sec=60)
    assert rl.can_trigger("p1") is True


def test_rate_limiter_blocks_within_cooldown():
    rl = RateLimiter(cooldown_sec=60)
    rl.record_trigger("p1")
    assert rl.can_trigger("p1") is False


def test_rate_limiter_allows_after_cooldown():
    rl = RateLimiter(cooldown_sec=60)
    past = datetime.now(timezone.utc) - timedelta(seconds=61)
    rl._last_trigger["p1"] = past
    assert rl.can_trigger("p1") is True


def test_sync_agent_poll_processes_chunks(db):
    chunks = [
        {
            "chunk_id": "c_001", "label": "WORK", "duration_sec": 1800,
            "confidence": 0.92, "started_at": "2026-04-14T09:00:00+00:00",
            "time_of_day": "morning",
        }
    ]
    mock_client = MagicMock()
    mock_client.fetch_chunks.return_value = (chunks, "c_001")

    agent = SyncAgent(
        db=db,
        tracker_client=mock_client,
        character_id="player_default",
        strategy=SessionStrategy(),
    )
    result = agent.poll()
    assert result == PollResult.OK

    # SessionStrategy gives 1 roll; the seeded WORK item has no label/confidence
    # requirement that blocks a WORK chunk with confidence=0.92, so there is always
    # exactly 1 eligible item and weighted_draw always returns it.
    ledger = db.execute("SELECT * FROM reward_ledger").fetchall()
    assert len(ledger) == 1
    assert ledger[0]["item_id"] == "work_common_001"


def test_sync_agent_poll_on_cooldown_returns_cooldown(db):
    mock_client = MagicMock()
    mock_client.fetch_chunks.return_value = ([], None)
    rl = RateLimiter(cooldown_sec=3600)
    rl.record_trigger("player_default")

    agent = SyncAgent(
        db=db,
        tracker_client=mock_client,
        character_id="player_default",
        strategy=SessionStrategy(),
        rate_limiter=rl,
    )
    result = agent.poll(manual=True)
    assert result == PollResult.ON_COOLDOWN


def test_sync_agent_poll_advances_cursor(db):
    chunks = [
        {
            "chunk_id": "c_001", "label": "GAME", "duration_sec": 3600,
            "confidence": 0.88, "started_at": "2026-04-14T20:00:00+00:00",
        }
    ]
    mock_client = MagicMock()
    mock_client.fetch_chunks.return_value = (chunks, "c_001")

    agent = SyncAgent(
        db=db,
        tracker_client=mock_client,
        character_id="player_default",
        strategy=SessionStrategy(),
    )
    agent.poll()
    cursor = db.execute(
        "SELECT last_cursor FROM sync_state WHERE player_id='default'"
    ).fetchone()["last_cursor"]
    assert cursor == "c_001"
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest services/tests/test_sync_agent.py -v
```

- [ ] **Step 3: Implement `services/sync_agent/rate_limiter.py`**

```python
from __future__ import annotations
from datetime import datetime, timezone


class RateLimiter:
    def __init__(self, cooldown_sec: int = 60) -> None:
        self.cooldown_sec = cooldown_sec
        self._last_trigger: dict[str, datetime] = {}

    def can_trigger(self, player_id: str) -> bool:
        last = self._last_trigger.get(player_id)
        if last is None:
            return True
        elapsed = (datetime.now(timezone.utc) - last).total_seconds()
        return elapsed >= self.cooldown_sec

    def record_trigger(self, player_id: str) -> None:
        self._last_trigger[player_id] = datetime.now(timezone.utc)
```

- [ ] **Step 4: Implement `services/sync_agent/tracker_client.py`**

```python
from __future__ import annotations
import httpx


class TrackerClient:
    """HTTP client for llm-activity-tracker /v1/chunks."""

    def __init__(self, base_url: str = "http://localhost:8000") -> None:
        self.base_url = base_url.rstrip("/")

    def fetch_chunks(
        self,
        after_cursor: str | None,
        limit: int = 50,
    ) -> tuple[list[dict], str | None]:
        """
        GET /v1/chunks?after_cursor=<id>&limit=<n>
        Returns (list_of_chunk_dicts, new_cursor_or_None).
        new_cursor is the last chunk_id in the response, or None if empty.
        """
        params: dict = {"limit": limit}
        if after_cursor:
            params["after_cursor"] = after_cursor

        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{self.base_url}/v1/chunks", params=params)
            response.raise_for_status()
            data = response.json()

        chunks: list[dict] = data if isinstance(data, list) else data.get("chunks", [])
        new_cursor = chunks[-1]["chunk_id"] if chunks else None
        return chunks, new_cursor
```

- [ ] **Step 5: Implement `services/sync_agent/agent.py`**

```python
from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timezone
from enum import Enum
from services.contracts.chunk import Chunk
from services.models.enums import Category
from services.models.item import ItemDefinition, DropRequirement, Effect
from services.models.place import Place, PlaceItemPool
from services.drop_engine.strategies import RollStrategy, SessionStrategy
from services.drop_engine.lottery import eligible_items, weighted_draw, DEFAULT_RARITY_WEIGHTS
from services.reward_ledger.ledger import record_drop
from services.progression.xp import award_category_xp, xp_for_chunk
from services.sync_agent.rate_limiter import RateLimiter
from services.sync_agent.tracker_client import TrackerClient


class PollResult(str, Enum):
    OK = "OK"
    ON_COOLDOWN = "ON_COOLDOWN"
    NO_NEW_CHUNKS = "NO_NEW_CHUNKS"


_SENTINEL_PLACE = Place(
    place_id="__global__", name="Global", place_type="global",
    item_pool=PlaceItemPool(),  # no filters
)


class SyncAgent:
    def __init__(
        self,
        db: sqlite3.Connection,
        tracker_client: TrackerClient,
        character_id: str,
        strategy: RollStrategy | None = None,
        rate_limiter: RateLimiter | None = None,
        min_confidence: float = 0.5,
    ) -> None:
        self.db = db
        self.tracker_client = tracker_client
        self.character_id = character_id
        self.strategy = strategy or SessionStrategy()
        self.rate_limiter = rate_limiter or RateLimiter(cooldown_sec=60)
        self.min_confidence = min_confidence

    def _get_cursor(self) -> str | None:
        row = self.db.execute(
            "SELECT last_cursor FROM sync_state WHERE player_id='default'"
        ).fetchone()
        return row["last_cursor"] if row else None

    def _save_cursor(self, cursor: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            """
            UPDATE sync_state SET last_cursor=?, last_sync_at=?
            WHERE player_id='default'
            """,
            (cursor, now),
        )
        self.db.commit()

    def _load_catalogue(self) -> list[ItemDefinition]:
        rows = self.db.execute("SELECT data FROM item_definitions").fetchall()
        result = []
        for row in rows:
            try:
                result.append(ItemDefinition.model_validate_json(row["data"]))
            except Exception:
                pass
        return result

    def _get_player_luck(self) -> int:
        row = self.db.execute(
            "SELECT luck FROM player_profile WHERE character_id=?",
            (self.character_id,),
        ).fetchone()
        return row["luck"] if row else 5

    def poll(self, manual: bool = False) -> PollResult:
        if manual and not self.rate_limiter.can_trigger(self.character_id):
            return PollResult.ON_COOLDOWN
        if manual:
            self.rate_limiter.record_trigger(self.character_id)

        cursor = self._get_cursor()
        chunk_dicts, new_cursor = self.tracker_client.fetch_chunks(after_cursor=cursor)

        if not chunk_dicts:
            return PollResult.NO_NEW_CHUNKS

        catalogue = self._load_catalogue()
        luck = self._get_player_luck()

        for raw in chunk_dicts:
            try:
                chunk = Chunk.model_validate(raw)
            except Exception:
                continue

            if chunk.confidence < self.min_confidence:
                continue

            # Award XP for the activity itself
            try:
                cat = Category(chunk.label)
                award_category_xp(
                    self.db,
                    character_id=self.character_id,
                    category=cat,
                    xp=xp_for_chunk(chunk),
                )
            except ValueError:
                pass  # unknown label — skip XP

            # Roll drops
            rolls = self.strategy.compute(chunk, luck)
            pool = eligible_items(catalogue, chunk, _SENTINEL_PLACE)

            for roll_n in range(rolls):
                winner = weighted_draw(pool, DEFAULT_RARITY_WEIGHTS, drop_weight_mods={})
                if winner:
                    record_drop(
                        self.db,
                        chunk_id=chunk.chunk_id,
                        roll_n=roll_n,
                        item=winner,
                        character_id=self.character_id,
                    )

        if new_cursor:
            self._save_cursor(new_cursor)

        return PollResult.OK
```

- [ ] **Step 6: Run — expect PASS**

```bash
pytest services/tests/test_sync_agent.py -v
```

Expected: 5 passed.

- [ ] **Step 7: Commit**

```bash
git add services/sync_agent/ services/tests/test_sync_agent.py
git commit -m "feat: add sync agent with rate limiter and tracker client"
```

---

## Task 14: FastAPI HTTP Layer

**Files:**
- Create: `services/api/main.py`
- Create: `services/api/routers/sync.py`
- Create: `services/api/routers/inventory.py`
- Create: `services/api/routers/player.py`
- Create: `services/api/routers/places.py`
- Create: `services/api/routers/notifications.py`
- Create: `services/tests/test_api.py`

- [ ] **Step 1: Write failing tests**

```python
# services/tests/test_api.py
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient
from services.storage.db import init_db
from services.models.enums import Category, Rarity, PlaceState, SlotType
from services.models.item import ItemDefinition, DropRequirement
from services.models.place import Place, PlaceItemPool, PlaceSlot
from services.place_service.service import save_place


@pytest.fixture
def seeded_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    visual = json.dumps({"base_sprite": "lumi.png", "evolution_stage": 0,
                         "skin": None, "accessories": [], "anim_state": "idle"})
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES (?, ?, ?)",
        ("player_default", "Lumi", visual),
    )
    conn.execute(
        "INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')"
    )
    conn.execute(
        "INSERT INTO player_category_xp (character_id, category, xp) VALUES (?, ?, ?)",
        ("player_default", "WORK", 300),
    )
    item = ItemDefinition(
        item_id="scroll_001", name="Scroll", category=Category.WORK,
        rarity=Rarity.COMMON, drop_requirement=DropRequirement(),
        icon="s.png", description="",
    )
    conn.execute(
        "INSERT INTO item_definitions (item_id, data) VALUES (?, ?)",
        (item.item_id, item.model_dump_json()),
    )
    conn.execute(
        """
        INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk)
        VALUES ('inv_001', 'player_default', 'scroll_001', '2026-04-14T00:00:00+00:00', 'c1')
        """
    )
    home = Place(
        place_id="home_001", name="Home", place_type="home",
        state=PlaceState.UNLOCKED,
        item_pool=PlaceItemPool(allowed_categories=[Category.WORK]),
        slots=[PlaceSlot(slot_id="s1", place_id="home_001", slot_type=SlotType.ITEM)],
    )
    save_place(conn, home)
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(seeded_db):
    from services.api.main import create_app
    app = create_app(db=seeded_db)
    return TestClient(app)


def test_get_sync_status(client):
    r = client.get("/sync/status")
    assert r.status_code == 200
    data = r.json()
    assert "last_cursor" in data
    assert "last_sync_at" in data


def test_get_player_profile(client):
    r = client.get("/player/profile")
    assert r.status_code == 200
    data = r.json()
    assert data["character_id"] == "player_default"
    assert data["total_xp"] == 300
    assert data["level"] >= 1
    assert "category_xp" in data


def test_get_inventory(client):
    r = client.get("/inventory")
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    assert len(items) == 1
    assert items[0]["item_id"] == "scroll_001"


def test_get_places(client):
    r = client.get("/places")
    assert r.status_code == 200
    places = r.json()
    assert len(places) == 1
    assert places[0]["place_id"] == "home_001"


def test_get_place_by_id(client):
    r = client.get("/places/home_001")
    assert r.status_code == 200
    assert r.json()["name"] == "Home"


def test_get_place_not_found(client):
    r = client.get("/places/nonexistent")
    assert r.status_code == 404


def test_get_pending_notifications_empty(client):
    r = client.get("/notifications/pending")
    assert r.status_code == 200
    assert r.json() == []


def test_ack_notification(client, seeded_db):
    import uuid
    nid = str(uuid.uuid4())
    seeded_db.execute(
        """
        INSERT INTO pending_notifications
            (notification_id, character_id, event_type, payload, created_at)
        VALUES (?, 'player_default', 'item_drop', '{}', '2026-04-14T00:00:00+00:00')
        """,
        (nid,),
    )
    seeded_db.commit()
    r = client.post(f"/notifications/{nid}/ack")
    assert r.status_code == 200
    row = seeded_db.execute(
        "SELECT acknowledged FROM pending_notifications WHERE notification_id=?", (nid,)
    ).fetchone()
    assert row["acknowledged"] == 1
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest services/tests/test_api.py -v
```

- [ ] **Step 3: Implement `services/api/main.py`**

```python
from __future__ import annotations
import sqlite3
from contextlib import asynccontextmanager
from fastapi import FastAPI
from services.storage.db import get_db
from services.api.routers import sync, inventory, player, places, notifications


def create_app(db: sqlite3.Connection | None = None) -> FastAPI:
    """Factory so tests can inject an in-memory db."""
    _db = db

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal _db
        if _db is None:
            _db = get_db()
        app.state.db = _db
        yield
        if db is None:  # only close if we opened it
            _db.close()

    app = FastAPI(title="LLM Activity Game Services", version="0.1.0", lifespan=lifespan)

    if db is not None:
        # For testing: set db on state immediately (lifespan won't run in TestClient)
        app.state.db = db

    app.include_router(sync.router, prefix="/sync", tags=["sync"])
    app.include_router(inventory.router, prefix="/inventory", tags=["inventory"])
    app.include_router(player.router, prefix="/player", tags=["player"])
    app.include_router(places.router, prefix="/places", tags=["places"])
    app.include_router(notifications.router, prefix="/notifications", tags=["notifications"])

    return app


app = create_app()
```

- [ ] **Step 4: Implement `services/api/routers/sync.py`**

```python
from fastapi import APIRouter, Request
from services.sync_agent.agent import SyncAgent, PollResult
from services.sync_agent.tracker_client import TrackerClient

router = APIRouter()


@router.get("/status")
def get_sync_status(request: Request):
    db = request.app.state.db
    row = db.execute("SELECT * FROM sync_state WHERE player_id='default'").fetchone()
    if row:
        return {"last_cursor": row["last_cursor"], "last_sync_at": row["last_sync_at"]}
    return {"last_cursor": None, "last_sync_at": None}


@router.post("/poll-now")
def poll_now(request: Request):
    db = request.app.state.db
    agent = SyncAgent(
        db=db,
        tracker_client=TrackerClient(),
        character_id="player_default",
    )
    result = agent.poll(manual=True)
    return {"result": result.value}
```

- [ ] **Step 5: Implement `services/api/routers/inventory.py`**

```python
from fastapi import APIRouter, Request

router = APIRouter()


@router.get("")
def get_inventory(request: Request):
    db = request.app.state.db
    rows = db.execute(
        "SELECT * FROM inventory WHERE character_id='player_default' ORDER BY acquired_at DESC"
    ).fetchall()
    return [dict(row) for row in rows]
```

- [ ] **Step 6: Implement `services/api/routers/player.py`**

```python
import json
from fastapi import APIRouter, Request, HTTPException
from services.progression.xp import get_total_xp, compute_level, compute_evolution_stage

router = APIRouter()


@router.get("/profile")
def get_player_profile(request: Request):
    db = request.app.state.db
    row = db.execute(
        "SELECT * FROM player_profile WHERE character_id='player_default'"
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Player not found")

    cat_rows = db.execute(
        "SELECT category, xp FROM player_category_xp WHERE character_id='player_default'"
    ).fetchall()
    category_xp = {r["category"]: r["xp"] for r in cat_rows}
    total_xp = get_total_xp(db, "player_default")
    level = compute_level(total_xp)
    stage = compute_evolution_stage(level)

    return {
        "character_id": row["character_id"],
        "name": row["name"],
        "total_xp": total_xp,
        "level": level,
        "evolution_stage": stage,
        "category_xp": category_xp,
        "visual": json.loads(row["visual"]),
        "equipped_items": json.loads(row["equipped_items"]),
    }
```

- [ ] **Step 7: Implement `services/api/routers/places.py`**

```python
from fastapi import APIRouter, Request, HTTPException
from services.place_service.service import get_place, list_places

router = APIRouter()


@router.get("")
def get_places(request: Request):
    db = request.app.state.db
    places = list_places(db)
    return [p.model_dump() for p in places]


@router.get("/{place_id}")
def get_place_by_id(place_id: str, request: Request):
    db = request.app.state.db
    place = get_place(db, place_id)
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")
    return place.model_dump()
```

- [ ] **Step 8: Implement `services/api/routers/notifications.py`**

```python
from fastapi import APIRouter, Request, HTTPException
from services.reward_ledger.ledger import get_pending_notifications

router = APIRouter()


@router.get("/pending")
def get_pending(request: Request):
    db = request.app.state.db
    rows = get_pending_notifications(db, "player_default")
    return [dict(row) for row in rows]


@router.post("/{notification_id}/ack")
def ack_notification(notification_id: str, request: Request):
    db = request.app.state.db
    result = db.execute(
        "UPDATE pending_notifications SET acknowledged=1 WHERE notification_id=?",
        (notification_id,),
    )
    db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"acknowledged": True}
```

- [ ] **Step 9: Run — expect PASS**

```bash
pytest services/tests/test_api.py -v
```

Expected: 8 passed.

- [ ] **Step 10: Commit**

```bash
git add services/api/ services/tests/test_api.py
git commit -m "feat: add FastAPI HTTP layer with sync, inventory, player, places, notifications endpoints"
```

---

## Task 15: Seed Data

**Files:**
- Create: `services/seeds/items.py`
- Create: `services/seeds/places.py`
- Create: `services/seeds/__main__.py`

- [ ] **Step 1: Implement `services/seeds/items.py`**

```python
"""Seed ItemDefinitions — one per rarity per representative category."""
from services.models.enums import Category, Rarity
from services.models.item import ItemDefinition, DropRequirement, Effect

SEED_ITEMS: list[ItemDefinition] = [
    # WORK
    ItemDefinition(
        item_id="focus_crystal_common", name="Focus Crystal",
        category=Category.WORK, rarity=Rarity.COMMON,
        drop_requirement=DropRequirement(activity_label="WORK", min_duration_sec=600),
        icon="focus_crystal_common.png",
        description="A small shard of concentrated effort.",
    ),
    ItemDefinition(
        item_id="focus_crystal_rare", name="Radiant Focus Crystal",
        category=Category.WORK, rarity=Rarity.RARE,
        drop_requirement=DropRequirement(activity_label="WORK", min_duration_sec=3600, min_confidence=0.85),
        effects=[Effect(effect_type="stat_buff", target="companion", params={"attack": 3})],
        icon="focus_crystal_rare.png",
        description="Forged from hours of deep work.",
    ),
    # GAME
    ItemDefinition(
        item_id="lucky_die_common", name="Lucky Die",
        category=Category.GAME, rarity=Rarity.COMMON,
        drop_requirement=DropRequirement(activity_label="GAME", min_duration_sec=600),
        icon="lucky_die.png",
        description="The sort of die you always roll first.",
    ),
    ItemDefinition(
        item_id="lucky_die_epic", name="Unstoppable Die",
        category=Category.GAME, rarity=Rarity.EPIC,
        drop_requirement=DropRequirement(activity_label="GAME", min_duration_sec=7200, min_confidence=0.9),
        effects=[Effect(effect_type="stat_buff", target="companion", params={"luck": 5})],
        icon="lucky_die_epic.png",
        description="Has never rolled a 1.",
    ),
    # SLEEP
    ItemDefinition(
        item_id="moonstone_common", name="Moonstone",
        category=Category.SLEEP, rarity=Rarity.COMMON,
        drop_requirement=DropRequirement(activity_label="SLEEP", min_duration_sec=14400, time_of_day="night"),
        icon="moonstone.png",
        description="Glows faintly with the memory of good rest.",
    ),
    ItemDefinition(
        item_id="dreamweave_legendary", name="Dreamweave Shard",
        category=Category.SLEEP, rarity=Rarity.LEGENDARY,
        drop_requirement=DropRequirement(activity_label="SLEEP", min_duration_sec=28800, min_confidence=0.95, time_of_day="night"),
        effects=[
            Effect(effect_type="companion_skin", target="companion", params={"skin": "dream_form"}),
        ],
        icon="dreamweave_legendary.png",
        description="A fragment of a perfect dream. Extremely rare.",
    ),
    # EXPLORE
    ItemDefinition(
        item_id="waystone_uncommon", name="Waystone",
        category=Category.EXPLORE, rarity=Rarity.UNCOMMON,
        drop_requirement=DropRequirement(activity_label="EXPLORE", min_duration_sec=900),
        icon="waystone.png",
        description="Still warm from distant roads.",
    ),
    # SOCIAL
    ItemDefinition(
        item_id="resonance_gem_uncommon", name="Resonance Gem",
        category=Category.SOCIAL, rarity=Rarity.UNCOMMON,
        drop_requirement=DropRequirement(activity_label="SOCIAL", min_duration_sec=600),
        icon="resonance_gem.png",
        description="Vibrates when held near people.",
    ),
    # VIDEO
    ItemDefinition(
        item_id="lightframe_common", name="Lightframe",
        category=Category.VIDEO, rarity=Rarity.COMMON,
        drop_requirement=DropRequirement(activity_label="VIDEO", min_duration_sec=1800),
        icon="lightframe.png",
        description="Captured from a moment of pure visual wonder.",
    ),
    # SPECIAL
    ItemDefinition(
        item_id="celestial_coin_rare", name="Celestial Coin",
        category=Category.SPECIAL, rarity=Rarity.RARE,
        drop_requirement=DropRequirement(min_confidence=0.8),   # any label, any place
        effects=[Effect(effect_type="home_unlock", target="home_system", params={"room": "vault"})],
        icon="celestial_coin.png",
        description="Appears without warning. Always meaningful.",
    ),
]
```

- [ ] **Step 2: Implement `services/seeds/places.py`**

```python
"""Seed the starting Home place — UNLOCKED, no occupants."""
from services.models.enums import Category, PlaceState, SlotType
from services.models.place import Place, PlaceItemPool, PlaceSlot

SEED_PLACES: list[Place] = [
    Place(
        place_id="home_study",
        name="The Study",
        place_type="home",
        description="A quiet room lit by a single lamp. Work happens here.",
        category=Category.WORK,
        state=PlaceState.UNLOCKED,
        item_pool=PlaceItemPool(
            allowed_categories=[Category.WORK, Category.SPECIAL],
        ),
        slots=[
            PlaceSlot(
                slot_id="study_slot_desk",
                place_id="home_study",
                slot_type=SlotType.ITEM,
                metadata={"label": "Desk", "position": {"x": 0.3, "y": 0.5}},
            ),
            PlaceSlot(
                slot_id="study_slot_shelf",
                place_id="home_study",
                slot_type=SlotType.ITEM,
                metadata={"label": "Shelf", "position": {"x": 0.7, "y": 0.3}},
            ),
        ],
        metadata={"theme": "study", "music": "calm_focus"},
    ),
]
```

- [ ] **Step 3: Implement `services/seeds/__main__.py`**

```python
"""
Run: python -m services.seeds [--db path/to/game.db]
Seeds item definitions, places, default player profile, and sync_state.
"""
import argparse
import json
import sys
from services.storage.db import get_db
from services.place_service.service import save_place
from services.seeds.items import SEED_ITEMS
from services.seeds.places import SEED_PLACES


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

    conn.commit()
    conn.close()
    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed game.db")
    parser.add_argument("--db", default="game.db", help="Path to game.db")
    args = parser.parse_args()
    seed(args.db)
```

- [ ] **Step 4: Verify seed runs without errors**

```bash
python -m services.seeds --db /tmp/test_game.db
```

Expected output:
```
Seeding into /tmp/test_game.db...
  10 item definitions seeded.
  1 places seeded.
  Default player profile seeded.
  Sync state initialized.
Done.
```

- [ ] **Step 5: Commit**

```bash
git add services/seeds/
git commit -m "feat: add seed data (10 items across all categories, home place, default player)"
```

---

## Task 16: Full Test Suite Pass

- [ ] **Step 1: Run all tests**

```bash
pytest -v
```

Expected: all tests pass, no warnings about missing modules.

- [ ] **Step 2: Check nothing is missing from spec**

Verify:
- `sync_agent` polls tracker, advances cursor, rate-limits manual triggers ✓
- `drop_engine` has configurable `RollStrategy`, weighted lottery, `DropRequirement` matching ✓
- Item/rarity system: `ItemDefinition`, `DropRequirement`, `Effect` registry, `InventoryItem` ✓
- `reward_ledger`: idempotent, keyed on `(chunk_id, roll_n)` ✓
- `pending_notifications`: Godot polling table ✓
- Character model: `Character`, `CharacterVisual`, `stat_mods` layer ✓
- `PlayerProfile` + `player_category_xp`: per-category XP, derived total/level ✓
- Universal `Place` model: three tables, seed one `place_type="home"` place ✓

- [ ] **Step 3: Run the server manually**

```bash
python -m services.seeds
uvicorn services.api.main:app --host 0.0.0.0 --port 8765 --reload
```

Verify in browser: `http://localhost:8765/docs` shows all endpoints.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: verify full MVP services suite passes"
```

---

## Running the Stack

```bash
# 1. Seed the database
python -m services.seeds

# 2. Start the game services API
uvicorn services.api.main:app --host 0.0.0.0 --port 8765 --reload

# 3. Manual sync trigger (simulates Godot "Check Rewards" button)
curl -X POST http://localhost:8765/sync/poll-now

# 4. Check player state
curl http://localhost:8765/player/profile

# 5. Check pending notifications
curl http://localhost:8765/notifications/pending
```

---

## What's Deferred (not in this plan)

| System | When |
|---|---|
| Godot client | After MVP services are stable |
| Home system service | Place tables ready; service logic deferred |
| Dungeon system | Character stats ready; service logic deferred |
| MCP server | Architecture designed; implementation deferred |
| Quest engine | `DropRequirement.extra` ready; engine not built |
| Automatic background polling (scheduler) | Use OS cron or APScheduler on top of `SyncAgent.poll()` |
