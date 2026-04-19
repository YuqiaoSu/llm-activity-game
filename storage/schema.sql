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
-- expires_at: NULL = permanent; ISO datetime = item expires then
CREATE TABLE IF NOT EXISTS inventory (
    instance_id   TEXT PRIMARY KEY,
    character_id  TEXT NOT NULL,
    item_id       TEXT NOT NULL,
    acquired_at   TEXT NOT NULL,
    source_chunk  TEXT NOT NULL,
    equipped      INTEGER NOT NULL DEFAULT 0,
    placed_in     TEXT,
    expires_at    TEXT
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
    metadata          TEXT NOT NULL DEFAULT '{}',
    xp                INTEGER NOT NULL DEFAULT 0,
    level             INTEGER NOT NULL DEFAULT 1
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

-- streak_state: tracks consecutive-day activity for the player
CREATE TABLE IF NOT EXISTS streak_state (
    player_id        TEXT PRIMARY KEY DEFAULT 'default',
    current_streak   INTEGER NOT NULL DEFAULT 0,
    longest_streak   INTEGER NOT NULL DEFAULT 0,
    last_active_date TEXT    -- ISO date YYYY-MM-DD of last day XP was earned; NULL = never
);

-- achievements: milestone definitions (seeded at startup)
CREATE TABLE IF NOT EXISTS achievements (
    achievement_id  TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT NOT NULL,
    condition_type  TEXT NOT NULL,  -- "total_xp" | "level" | "streak" | "items_collected"
    threshold       INTEGER NOT NULL
);

-- player_achievements: which milestones each player has unlocked
CREATE TABLE IF NOT EXISTS player_achievements (
    player_id       TEXT NOT NULL,
    achievement_id  TEXT NOT NULL REFERENCES achievements(achievement_id),
    unlocked_at     TEXT NOT NULL,
    PRIMARY KEY (player_id, achievement_id)
);

-- pinned_achievements: up to 3 achievements a player has chosen to showcase
-- pin_order (1–3) controls display order; UNIQUE per player+achievement pair.
CREATE TABLE IF NOT EXISTS pinned_achievements (
    player_id       TEXT NOT NULL DEFAULT 'player_default',
    achievement_id  TEXT NOT NULL REFERENCES achievements(achievement_id),
    pin_order       INTEGER NOT NULL DEFAULT 1,
    pinned_at       TEXT NOT NULL,
    PRIMARY KEY (player_id, achievement_id)
);

-- weekly_challenges: rotating weekly goal definitions (seeded at startup)
CREATE TABLE IF NOT EXISTS weekly_challenges (
    challenge_id  TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    description   TEXT NOT NULL,
    category      TEXT NOT NULL,   -- Category value for 'xp' metric; 'ALL' for cross-category metrics
    metric        TEXT NOT NULL,   -- 'xp' | 'total_xp' | 'categories'
    threshold     INTEGER NOT NULL
);

-- player_weekly_progress: per-player progress row per challenge per ISO week
-- week_start is the Monday of the week (YYYY-MM-DD); acts as automatic weekly reset
CREATE TABLE IF NOT EXISTS player_weekly_progress (
    player_id     TEXT NOT NULL,
    challenge_id  TEXT NOT NULL REFERENCES weekly_challenges(challenge_id),
    week_start    TEXT NOT NULL,
    progress      INTEGER NOT NULL DEFAULT 0,
    completed     INTEGER NOT NULL DEFAULT 0,
    reward_given  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (player_id, challenge_id, week_start)
);

-- collection_log: tracks the first time a player acquires each distinct item type
CREATE TABLE IF NOT EXISTS collection_log (
    player_id    TEXT NOT NULL,
    item_id      TEXT NOT NULL REFERENCES item_definitions(item_id),
    first_seen_at TEXT NOT NULL,
    PRIMARY KEY (player_id, item_id)
);

-- weekly_reroll_state: one free reroll per player per ISO week
-- rerolled_challenge_id records which challenge was swapped out (for history)
CREATE TABLE IF NOT EXISTS weekly_reroll_state (
    player_id              TEXT NOT NULL,
    week_start             TEXT NOT NULL,
    rerolled_challenge_id  TEXT,
    rerolled_at            TEXT NOT NULL,
    PRIMARY KEY (player_id, week_start)
);

-- daily_goals: short-lived (24h) activity targets auto-generated from the suggestion engine.
-- date is the UTC calendar date (YYYY-MM-DD); one row per (player_id, date, category).
-- progress_sec accumulates active seconds in that category during the day.
CREATE TABLE IF NOT EXISTS daily_goals (
    goal_id       TEXT PRIMARY KEY,
    player_id     TEXT NOT NULL DEFAULT 'player_default',
    date          TEXT NOT NULL,         -- UTC date YYYY-MM-DD
    category      TEXT NOT NULL,
    target_sec    INTEGER NOT NULL,      -- target active seconds (converted from suggestion target_min)
    progress_sec  INTEGER NOT NULL DEFAULT 0,
    completed     INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    UNIQUE (player_id, date, category)
);

-- place_perks: permanent XP boosts donated to a place by sacrificing an item.
-- A perk survives slot changes (not stored in place_active_effects).
-- UNIQUE(place_id, item_id) prevents donating the same item type twice.
CREATE TABLE IF NOT EXISTS place_perks (
    perk_id       TEXT PRIMARY KEY,
    place_id      TEXT NOT NULL REFERENCES places(place_id),
    item_id       TEXT NOT NULL,              -- donated item type
    instance_id   TEXT NOT NULL,              -- consumed instance_id (history only)
    boost_factor  REAL NOT NULL DEFAULT 0.10, -- additive factor on top of base effect
    donated_at    TEXT NOT NULL,
    UNIQUE(place_id, item_id)
);

-- challenge_events: limited-window XP multiplier events per category
-- category may be 'ALL' to apply to every category.
-- multiplier is applied to base XP when a chunk falls within [starts_at, ends_at].
CREATE TABLE IF NOT EXISTS challenge_events (
    event_id    TEXT PRIMARY KEY,
    label       TEXT NOT NULL,           -- display name, e.g. "Focus Weekend"
    category    TEXT NOT NULL,           -- Category value or 'ALL'
    multiplier  REAL NOT NULL DEFAULT 2.0,
    starts_at   TEXT NOT NULL,           -- ISO datetime (UTC)
    ends_at     TEXT NOT NULL            -- ISO datetime (UTC)
);

-- trade_offers: static NPC exchange offers (exchange N items of one rarity for 1 of another)
-- from_category / to_category are nullable; NULL means any category accepted / random output.
CREATE TABLE IF NOT EXISTS trade_offers (
    offer_id       TEXT PRIMARY KEY,
    trader_name    TEXT NOT NULL,        -- NPC display name
    label          TEXT NOT NULL,        -- human-readable e.g. "3× Common → 1 Uncommon"
    from_rarity    TEXT NOT NULL,        -- rarity tier given up (COMMON/UNCOMMON/RARE/EPIC/LEGENDARY)
    from_qty       INTEGER NOT NULL,     -- how many items of from_rarity needed
    from_category  TEXT,                 -- optional: restrict source items to this category
    to_rarity      TEXT NOT NULL,        -- rarity tier received
    to_qty         INTEGER NOT NULL DEFAULT 1,
    to_category    TEXT                  -- optional: restrict output item to this category
);

-- wishlist: items a player wants to receive as drops
CREATE TABLE IF NOT EXISTS wishlist (
    player_id  TEXT NOT NULL DEFAULT 'player_default',
    item_id    TEXT NOT NULL REFERENCES item_definitions(item_id),
    added_at   TEXT NOT NULL,
    PRIMARY KEY (player_id, item_id)
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

CREATE TABLE IF NOT EXISTS skills (
    skill_id        TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    xp_cost         INTEGER NOT NULL DEFAULT 100,
    effect_type     TEXT NOT NULL,
    effect_params   TEXT NOT NULL DEFAULT '{}',
    max_level       INTEGER NOT NULL DEFAULT 3
);

CREATE TABLE IF NOT EXISTS player_skills (
    player_id       TEXT NOT NULL,
    skill_id        TEXT NOT NULL REFERENCES skills(skill_id),
    unlocked_at     TEXT NOT NULL,
    level           INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (player_id, skill_id)
);

-- player_settings: per-player configurable preferences
CREATE TABLE IF NOT EXISTS player_settings (
    player_id           TEXT PRIMARY KEY DEFAULT 'player_default',
    daily_xp_target     INTEGER NOT NULL DEFAULT 100
);
