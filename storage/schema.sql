-- sync_state: one row per player, tracks cursor into tracker
CREATE TABLE IF NOT EXISTS sync_state (
    player_id            TEXT PRIMARY KEY DEFAULT 'default',
    last_cursor          TEXT,
    last_sync_at         TEXT,
    last_manual_poll_at  TEXT
);

-- item_definitions: catalogue of all item templates (loaded from seeds)
CREATE TABLE IF NOT EXISTS item_definitions (
    item_id  TEXT PRIMARY KEY,
    data     TEXT NOT NULL
);

-- inventory: items owned by a player character
CREATE TABLE IF NOT EXISTS inventory (
    instance_id   TEXT PRIMARY KEY,
    character_id  TEXT NOT NULL,
    item_id       TEXT NOT NULL,
    acquired_at   TEXT NOT NULL,
    source_chunk  TEXT NOT NULL,
    equipped      INTEGER NOT NULL DEFAULT 0,
    placed_in     TEXT
);

-- reward_ledger: idempotent drop log; (chunk_id, roll_n) prevents re-award on replay
CREATE TABLE IF NOT EXISTS reward_ledger (
    ledger_id     TEXT PRIMARY KEY,
    chunk_id      TEXT NOT NULL,
    roll_n        INTEGER NOT NULL,
    item_id       TEXT NOT NULL,
    character_id  TEXT NOT NULL,
    awarded_at    TEXT NOT NULL,
    UNIQUE (chunk_id, roll_n)
);

-- pending_notifications: reward events waiting for Godot to acknowledge
CREATE TABLE IF NOT EXISTS pending_notifications (
    notification_id  TEXT PRIMARY KEY,
    character_id     TEXT NOT NULL,
    event_type       TEXT NOT NULL,
    payload          TEXT NOT NULL,
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
    stat_mods      TEXT NOT NULL DEFAULT '{}',
    visual         TEXT NOT NULL,
    equipped_items TEXT NOT NULL DEFAULT '[]'
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
    category          TEXT,
    state             TEXT NOT NULL DEFAULT 'LOCKED',
    unlock_condition  TEXT,
    item_pool         TEXT NOT NULL,
    connected_to      TEXT NOT NULL DEFAULT '[]',
    parent_place      TEXT,
    metadata          TEXT NOT NULL DEFAULT '{}'
);

-- place_slots: slots within a place
CREATE TABLE IF NOT EXISTS place_slots (
    slot_id      TEXT PRIMARY KEY,
    place_id     TEXT NOT NULL REFERENCES places(place_id),
    slot_type    TEXT NOT NULL,
    accepts      TEXT,
    occupant_id  TEXT,
    metadata     TEXT NOT NULL DEFAULT '{}'
);

-- chunk_log: one row per processed tracker chunk — used for activity history screen
CREATE TABLE IF NOT EXISTS chunk_log (
    log_id        TEXT PRIMARY KEY,
    chunk_id      TEXT NOT NULL UNIQUE,   -- idempotent; INSERT OR IGNORE on replay
    category      TEXT NOT NULL,
    xp_awarded    INTEGER NOT NULL,
    duration_sec  INTEGER NOT NULL,
    processed_at  TEXT NOT NULL
);

-- place_active_effects: materialised effects from filled slots; rebuilt on slot change
CREATE TABLE IF NOT EXISTS place_active_effects (
    effect_id       TEXT PRIMARY KEY,
    place_id        TEXT NOT NULL REFERENCES places(place_id),
    source_slot_id  TEXT NOT NULL REFERENCES place_slots(slot_id),
    effect_type     TEXT NOT NULL,
    params          TEXT NOT NULL DEFAULT '{}',
    applied_at      TEXT NOT NULL
);
