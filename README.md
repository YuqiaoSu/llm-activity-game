# LLM Activity Game

This repository is the future player-facing game and gamification product built on top of `llm-activity-tracker`.

It is intentionally a clean post-split shell: the copied tracker runtime, tests, packaging files, and tracker-specific docs have been removed so this repo can grow in its own direction.

Start with [docs/gamification-overview.md](docs/gamification-overview.md).

## Current Focus

- define the tracker-to-game sync contract
- choose the game client stack
- design progression, rewards, quests, and retention systems
- establish game-owned storage, assets, and Steam release flows

## Repository Layout

```text
assets/        Game-owned art, audio, and brand assets
contracts/     Tracker-to-game integration contracts
docs/          Product and architecture direction
game-client/   Player-facing client implementation
services/      Sync, rewards, progression, and profile services
steam/         Steam packaging and release materials
storage/       Game database schema and migrations
```

## Current State

- `llm-activity-tracker` remains the source of truth for capture and classification
- this repo now owns only game-facing planning and scaffolding
- gameplay code has not been implemented yet

## License

Private / unreleased.
