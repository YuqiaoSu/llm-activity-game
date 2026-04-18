# LLM Activity Game - Gamification Overview

## Goal

This repository is the future player-facing product that sits on top of the tracker pipeline.

Its job is not to capture or classify raw activity. Its job is to turn trusted tracker outputs into:

- progression
- rewards
- quests
- streaks
- unlocks
- player-facing presentation
- Steam-ready packaging and distribution

The repository has been cleaned into a game-oriented shell so implementation can start from clear boundaries. It should now evolve as an independent product repo with its own runtime, assets, storage, and release process.

## Relationship to the tracker repo

`llm-activity-tracker` remains the source of truth for:

- raw activity capture
- archived sessions
- chunk aggregation
- rule-based categorization
- LLM-assisted categorization
- evaluation and research workflows

`llm-activity-game` should consume tracker outputs rather than re-owning those concerns.

The clean seam is the classified activity chunk.

## Product direction

The game layer should reward sustained and meaningful activity without distorting the underlying tracker into a game-first codebase.

Good candidate directions:

- cozy companion or pet growth
- town-building or room-building progression
- quest and streak system over real activity
- run energy for a lightweight roguelite or deckbuilder

The exact genre can evolve, but the backend responsibilities stay similar.

## Core systems this repo will eventually need

### Player progression

- player profile
- XP and level curves
- currencies or tokens
- unlock tracks
- cosmetic or character state

### Rewarding

- reward rules driven by classified chunks
- confidence thresholds before a chunk is eligible
- daily caps and anti-idle safeguards
- idempotent reward ledger keyed by `chunk_id`

### Retention systems

- daily quests
- weekly quests
- streak rules
- achievement milestones
- notification feed and claim flow

### Presentation

- game client or companion client
- player HUD and menus
- inventory and progression views
- reward animation and feedback
- audio, art, and UI themes

## Recommended architecture

## Split of responsibility

```text
llm-activity-tracker
  -> owns capture, storage, classification, evaluation

llm-activity-game
  -> owns sync, rewards, progression, presentation, Steam
```

## Communication model

Prefer local HTTP between the two repos.

Recommended future tracker endpoints:

- `GET /v1/meta`
- `GET /v1/chunks?after_cursor=...&limit=...`
- `GET /v1/snapshot`
- `GET /v1/day-summary?date=YYYY-MM-DD&interval=5`
- `GET /v1/health`

Each synced chunk should eventually include:

- `chunk_id`
- `chunk_start`
- `chunk_end`
- `interval_min`
- `label`
- `confidence`
- `source`
- `keystrokes`
- `mouse_events`
- `idle_sec`
- `apps`
- `domains`

## Database strategy

Use separate databases.

- tracker repo owns `tracker.db`
- game repo owns `game.db`

`game.db` should eventually contain:

- `sync_state`
- `player_profile`
- `reward_ledger`
- `xp_ledger`
- `inventory_items`
- `quests`
- `streaks`
- `achievements`

The game repo should never write into the tracker database.

## Suggested future folder shape

```text
llm-activity-game/
  game-client/
  services/
    sync_agent/
    reward_engine/
    progression/
    profile/
  storage/
    schema.sql
    migrations/
  assets/
    art/
    audio/
    marketing/
  steam/
  docs/
    gamification-overview.md
    economy.md
    steam-release.md
    art-direction.md
```

## Art and design requirements

Before implementation is serious, this repo will need a product identity:

- visual theme
- character or world direction
- item and reward language
- UI/HUD style
- sound style
- Steam capsule art and screenshots

If the first release targets Steam community appeal, the game loop should be easy to explain visually and easy to screenshot.

## Steam distribution model

The likely release shape is:

- ship the game as the public Steam app
- bundle or install the tracker runtime as a local companion component
- keep Steam achievements, cloud saves, and community-facing features in this repo only

This repo should eventually own:

- Steam build scripts
- Steam branches and depots
- achievements and stats mapping
- save/export policy for `game.db`
- release notes and store-facing assets

## Immediate scope after cleanup

This cleanup does not add gameplay code yet.

The repository is intentionally left as a product shell with docs, owned asset space, and implementation placeholders.

The next useful steps in this repo are:

1. decide the product direction
2. define `game.db`
3. define the tracker-to-game sync contract
4. choose the game client stack
5. design the reward and progression model

That keeps the game work separate while still reusing the tracker's strongest asset: structured, classified activity data.
