# LLM Activity Game — Feature Reference

> **Stack:** Python 3.11 · FastAPI · SQLite · Godot 4 (GDScript client)
> **Architecture:** 19 FastAPI routers · SyncAgent background poller · SQLite (35+ tables) · Godot frontend

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Sync & Tracker Integration](#1-sync--tracker-integration)
3. [Player Profile & Progression](#2-player-profile--progression)
4. [Inventory & Items](#3-inventory--items)
5. [Places System](#4-places-system)
6. [Drop Engine & Rarity](#5-drop-engine--rarity)
7. [Challenges & Daily Goals](#6-challenges--daily-goals)
8. [Skills Tree](#7-skills-tree)
9. [Achievements](#8-achievements)
10. [Notifications](#9-notifications)
11. [Analytics & History](#10-analytics--history)
12. [Leaderboard & Ghosts](#11-leaderboard--ghosts)
13. [Trading & Crafting](#12-trading--crafting)
14. [Catalogue & Wishlist](#13-catalogue--wishlist)
15. [Feed & Journal](#14-feed--journal)
16. [Database Schema](#15-database-schema-tables)

---

## System Overview

The game converts real-life computer activity tracked by `llm-activity-tracker` into a companion RPG. Activity chunks (5-minute aggregates labelled `WORK / GAME / VIDEO / SOCIAL / EXPLORE / SLEEP`) are fetched every 5 minutes by the `SyncAgent`, which awards XP, triggers item drops, and advances all game state.

```
llm-activity-tracker ──► SyncAgent (300 s poll)
                               │
              ┌────────────────┼──────────────────┐
              ▼                ▼                  ▼
          XP + Level        Item Drops       Place Effects
              │                │                  │
     Streaks / Decay       Notifications    Set Bonuses / Perks
              │
         Challenges / Goals / Achievements
              │
         FastAPI (19 routers) ──► Godot 4 Client
```

---

## 1. Sync & Tracker Integration

**Router:** `GET/POST /sync/*`

| Endpoint | Purpose |
|----------|---------|
| `GET /sync/status` | Last cursor, last sync timestamp |
| `POST /sync/poll-now` | Manually trigger a poll (rate-limited with adaptive cooldown) |
| `GET /sync/multipliers` | All active XP multipliers and their sources |

**SyncAgent poll order (8 steps):**
1. Rate-limit check
2. Daily XP decay / dormancy recovery flag
3. Fetch new chunks from tracker API
4. Load active place effects, skill bonuses, set bonuses
5. Compute full XP multiplier stack
6. Per-chunk: award category XP, update goals, roll item drops, check level-ups, update place XP
7. Update streaks, achievements, weekly/daily challenge progress
8. Save cursor (idempotent — chunk replay is safe)

**XP Multiplier Sources:**
- Activity streak ≥ 3 days: ×1.1
- Dormancy recovery: ×1.5 (consumed after first earned chunk)
- Place slot effects: per-place xp_multiplier effects
- Set bonuses: +25% when all items of a named set are slotted
- Challenge events: time-windowed per-category or global multipliers
- Combo bonus: ×1.1 when 3+ categories earn XP in one poll
- Skill effects: passive drop_weight_mod and xp_multiplier

---

## 2. Player Profile & Progression

**Router:** `GET/PATCH /player/*`

### Levels & Evolution

| Tier | Levels | Stage Name |
|------|--------|-----------|
| 1–5 | Hatchling | Early game |
| 6–15 | Growing | Mid game |
| 16–30 | Mature | Late game |
| 31+ | Legendary | Endgame |

**XP thresholds (cumulative):** 0 → 100 → 250 → 500 → 900 → 1,400 → 2,000 → 2,750 → 3,600 → 4,600

### Profile Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /player/profile` | Full snapshot: XP, level, evolution, streak, mood, category breakdown, equipped items/title |
| `PATCH /player/profile` | Rename companion (1–24 chars) |
| `GET /player/settings` | Daily XP target, goal difficulty scale |
| `PATCH /player/settings` | Update settings |
| `GET /player/luck` | Current luck stat and next upgrade cost |
| `POST /player/luck/upgrade` | Spend XP to raise luck (max 20; cost doubles per level) |
| `GET /player/titles` | All titles with earned/equipped status |
| `POST /player/titles/{id}/equip` | Equip a title |
| `GET /player/xp-projection` | Days to next level-up (7-day average) |
| `GET /player/focus-streak` | Consecutive WORK/LEARN days |
| `GET /player/streak-freeze` | Freeze charges remaining and cost |
| `POST /player/streak-freeze/buy` | Buy a streak freeze (max 3; cost: 100 → 200 → 400 XP) |
| `GET /player/mood` | Self-set mood and current drop multiplier |
| `PATCH /player/mood` | Set mood: `happy / neutral / sad / anxious` |
| `GET /player/login-streak` | Daily login streak and next reward milestone |
| `POST /player/login-checkin` | Record daily login (10 XP + 100 bonus every 7 days) |
| `GET /player/daily-tip` | Contextual tip, deterministic per calendar day |
| `GET /player/export` | Full data snapshot (profile, inventory, achievements, places, skills, 7-day XP) |
| `GET /player/season` | Monthly tier (BRONZE / SILVER / GOLD) and days remaining |
| `GET /player/journal` | Major milestones, newest-first |
| `GET /player/timeline` | Significant events (level-ups, achievements, place unlocks) |
| `GET /player/mastery` | Category mastery tiers sorted by XP |

### Luck System
- Base luck: 5 · Max: 20
- Scales non-COMMON drop rarity weights by `(luck / 10) ^ 0.5`
- Luck 10 (midpoint) is neutral (factor = 1.0); luck 20 gives ×1.41 to rare tiers

### Season Tiers (monthly)
| Tier | Monthly XP |
|------|-----------|
| BRONZE | 0+ |
| SILVER | 500+ |
| GOLD | 2,000+ |

---

## 3. Inventory & Items

**Router:** `GET/POST/PATCH/DELETE /inventory/*`

### Item Properties
- **Rarity:** COMMON · UNCOMMON · RARE · EPIC · LEGENDARY
- **Durability:** 0–100, decreases 10 points when placed in a slot; restored via repair
- **Expiry:** `expires_at` timestamp or NULL (permanent)
- **Tags:** Up to 3 user-defined tags (12 chars each)
- **Flags:** `favorite`, `locked` (prevents accidental sale/deletion)
- **Note:** 50-char freetext annotation per instance

### Inventory Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /inventory` | List items grouped by item_id with quantity, rarity, tags |
| `DELETE /inventory/instances/{id}` | Discard item instance |
| `POST /inventory/instances/{id}/sell` | Sell for XP (see rarity table below) |
| `GET /inventory/instances/{id}/sell-value` | Preview sell value |
| `PATCH /inventory/instances/{id}/favorite` | Toggle favorite |
| `PATCH /inventory/instances/{id}/note` | Attach note |
| `PATCH /inventory/instances/{id}/lock` | Lock against sale |
| `PATCH /inventory/instances/{id}/tags` | Manage tags |
| `POST /inventory/instances/{id}/repair` | Restore durability to 100 (costs XP) |
| `POST /inventory/bulk-sell` | Sell all unlocked/unplaced instances by rarity ± category |
| `POST /inventory/bulk-repair` | Repair all worn items in batch |
| `POST /inventory/batch-tag` | Apply tags to up to 50 instances |
| `PATCH /inventory/{id}/equip` | Toggle equipped flag for all copies of item_id |
| `POST /inventory/fuse` | 3× same-item copies → 1 next-rarity item |
| `POST /inventory/upgrade` | 2× same-category items → 1 higher-rarity item |
| `GET /inventory/upgrade-cost` | Preview items needed for target rarity |
| `GET /inventory/value-summary` | Aggregate inventory value by rarity |
| `GET /inventory/age-histogram` | Item counts and value by acquisition age buckets |
| `GET /inventory/recipes` | Available crafting recipes based on current inventory |
| `GET /inventory/drop-odds` | Drop probability per item in category |
| `GET /inventory/expiring` | Items expiring within N days (default 7) |
| `GET /inventory/crafting-history` | Audit log of upgrades/crafts |
| `GET /inventory/rarity-stats` | Per-rarity counts and percentages |
| `GET /inventory/tags` | All distinct tags the player has used |
| `GET /inventory/sets` | Named item sets with per-item ownership status |

### Sell Values
| Rarity | XP | Vintage bonus (30+ days old) |
|--------|----|------------------------------|
| COMMON | 5 | +20% |
| UNCOMMON | 15 | +20% |
| RARE | 30 | +20% |
| EPIC | 60 | +20% |
| LEGENDARY | 100 | +20% |

---

## 4. Places System

**Router:** `GET/PUT/POST /places/*`

Places are unlockable locations where items can be slotted to generate passive XP bonuses. Each place has typed slots, a category preference, a level that advances via invested XP, and a visit streak.

### Place States: `LOCKED → UNLOCKED → ACTIVE → COMPLETED`

### Place Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /places` | All places enriched with slots, perks, set bonuses, unlock progress |
| `GET /places/{id}` | Single place detail |
| `PUT /places/{id}/slots/{slot_id}` | Assign / remove item from slot |
| `POST /places/{id}/visit` | Record visit, update visit streak, award milestone rewards |
| `POST /places/{id}/invest` | Spend XP to advance place level (daily cap: 500 XP/place) |
| `POST /places/{id}/donate` | Donate item as permanent +10% XP perk (place level ≥5 required) |
| `POST /places/{id}/gift-item` | Convert item to place XP |
| `GET /places/{id}/slot-recommend` | Best unplaced item per empty slot |
| `GET /places/{id}/slot-stats` | Fill %, category-match % |
| `GET /places/{id}/upgrade-preview` | Cost-benefit projection before investing |
| `GET /places/{id}/history` | Recent invest/donate/slot activity log |
| `GET /places/{id}/visits` | Visit history, newest-first |
| `GET /places/{id}/slot-history` | Slot assignment audit trail |
| `GET /places/leaderboard` | Places ranked by total XP earned |

### Place Leveling
```
XP threshold = level² × 100
Level = floor(sqrt(place_xp / 100))
```

### Slot System
- Slot types: `ITEM`, `CHARACTER`, `ANY`
- Each slot has optional category filter (e.g., Gym accepts WORK items only)
- Placing an item decreases its durability by 10
- Active effects rebuild on every slot change

### Place Perks & Set Bonuses
- **Perk:** donate an item → permanent +10% XP multiplier at that place (one per item type)
- **Set bonus:** slot all items of a named set → +25% XP multiplier while complete
- **Visit streak milestones:** 3 / 7 / 14 consecutive days → random item reward

---

## 5. Drop Engine & Rarity

**File:** `services/drop_engine/lottery.py`

### Default Rarity Weights
| Rarity | Base weight |
|--------|------------|
| COMMON | 60.0 |
| UNCOMMON | 25.0 |
| RARE | 10.0 |
| EPIC | 4.0 |
| LEGENDARY | 1.0 |

Non-COMMON weights are scaled by `(luck / 10) ^ 0.5`. At max luck (20), rare tiers get ×1.41.

### Drop Requirements (per item definition)
- `activity_label`: must match chunk label (e.g., only drops from WORK chunks)
- `min_duration_sec`: chunk must be long enough
- `min_confidence`: classifier confidence threshold
- `time_of_day`: `dawn / day / dusk / night` filter

### Place Item Pool Filtering
- `explicit_items`: whitelist specific item IDs
- `allowed_categories` / `allowed_rarities`: restrict by tier
- `SPECIAL` category always passes category filter

---

## 6. Challenges & Daily Goals

### Weekly Challenges

**Router:** `GET/POST /challenges/*`

| Endpoint | Purpose |
|----------|---------|
| `GET /challenges` | Weekly challenges with progress |
| `GET /challenges/daily-bonus` | Today's 2× XP highlight challenge |
| `GET /challenges/ghosts` | Ghost player leaderboard (FocusBot / CasualMax / XP Grinder) |
| `POST /challenges/{id}/claim` | Claim reward (50 XP + notification) |
| `POST /challenges/{id}/reroll` | Swap challenge (one free reroll per ISO week) |

**Challenge metrics:** `xp` (per category) · `total_xp` (all categories) · `categories` (distinct active categories)

### Daily Goals

**Router:** `GET/POST /goals/*`

| Endpoint | Purpose |
|----------|---------|
| `GET /goals/daily` | Today's auto-generated goals (target_sec, progress_sec, completed) |
| `GET /goals/streak` | Goal completion streak and next milestone (7 / 14 / 30 days) |
| `GET /goals/stats` | All-time completion stats by category |
| `POST /goals/claim-streak-reward` | Trigger milestone item award if eligible |

Goals are auto-generated daily (one per active category), with duration scaled by `goal_difficulty_scale` (0.5–2.0, configurable per player).

---

## 7. Skills Tree

**Router:** `GET/POST /skills/*`

| Endpoint | Purpose |
|----------|---------|
| `GET /skills` | All skills with unlock/level status, costs, can_upgrade flags |
| `POST /skills/{id}/unlock` | Unlock skill by spending XP |
| `POST /skills/{id}/upgrade` | Upgrade to next tier |

**Upgrade cost:** `xp_cost × 2^current_level` per tier  
**Effect types:** `xp_multiplier` · `drop_weight_mod` · `category_xp_bonus`  
**Max levels:** per-skill cap (typically 3)

---

## 8. Achievements

**Router:** `GET/POST/DELETE /achievements/*`

| Endpoint | Purpose |
|----------|---------|
| `GET /achievements` | All achievements with unlock status, progress, chain depth |
| `POST /achievements/{id}/pin` | Pin achievement (max 3 pinned) |
| `DELETE /achievements/{id}/unpin` | Remove from pins |

**Condition types:** `total_xp` · `level` · `streak` · `items_collected`  
**Chain system:** parent achievement must unlock before child becomes visible

---

## 9. Notifications

**Router:** `GET/POST /notifications/*`

| Endpoint | Purpose |
|----------|---------|
| `GET /notifications/count` | Unread count |
| `GET /notifications/pending` | All unacknowledged notifications |
| `GET /notifications/inbox` | Full inbox (read + unread), optional event_type filter |
| `POST /notifications/{id}/ack` | Mark single notification read |
| `POST /notifications/ack-all` | Mark all read |
| `GET /notifications/prefs` | Mute preferences per event type |
| `PATCH /notifications/prefs/{type}` | Mute / unmute an event type |
| `GET /notifications/summary` | Per-type counts and recency (top 10 types) |
| `POST /notifications/ack-by-type` | Bulk-acknowledge all of a specific event type |

**Event types:** `item_drop` · `level_up` · `achievement_unlock` · `place_unlock` · `place_level_up` · `challenge_complete` · and more

---

## 10. Analytics & History

### Activity History

**Router:** `GET /history/*`

| Endpoint | Purpose |
|----------|---------|
| `GET /history/daily` | Per-day XP and duration by category (last N days, default 14) |
| `GET /history/heatmap` | Per-day intensity tiers 0–4 for heatmap visualization (last N weeks, default 12) |

**Heatmap tiers:** 0 = none · 1 = low (1–30 XP) · 2 = medium (31–80) · 3 = high (81–180) · 4 = very high (180+ XP)

### Stats

**Router:** `GET /stats/*`

| Endpoint | Purpose |
|----------|---------|
| `GET /stats` | Core stats: total XP, level, evolution, category XP, chunks processed, drops, places unlocked, streak |
| `GET /stats/summary` | All-time summary: peak week XP, items collected, achievement count |

### Recap

**Router:** `GET /recap/*`

| Endpoint | Purpose |
|----------|---------|
| `GET /recap/daily` | Today: total XP, active minutes, category breakdown, drops, goals, streak |
| `GET /recap/weekly` | This week: total XP, active minutes, category breakdown |

---

## 11. Leaderboard & Ghosts

**Router:** `GET /leaderboard/*`

| Endpoint | Purpose |
|----------|---------|
| `GET /leaderboard/weekly` | Personal weekly XP history (last N weeks) |
| `GET /leaderboard/monthly` | Monthly tier progression (BRONZE / SILVER / GOLD) |

**Ghost players (deterministic fixtures):**
| Ghost | Weekly XP | Level | Streak | Style |
|-------|-----------|-------|--------|-------|
| FocusBot | 520 | 8 | 7 days | Focused on WORK |
| CasualMax | 110 | 4 | 2 days | Balanced, casual |
| XP Grinder | 1,200 | 15 | 21 days | Grinds all categories |

---

## 12. Trading & Crafting

### Craft

**Router:** `POST /inventory/craft`

Combine two different items of the same category → one higher-rarity item of that category.

### Fuse

**Router:** `POST /inventory/fuse`

Combine 3 copies of the same item → 1 random item of the next rarity tier.

### Trade

**Router:** `GET/POST /trade/*`

| Endpoint | Purpose |
|----------|---------|
| `GET /trade/offers` | NPC trade offers with affordability |
| `POST /trade/accept` | Execute trade (consume from_qty → grant to_qty) |

Example trade: 3× COMMON → 1 UNCOMMON (NPC-defined exchanges, optional category filters).

### Rarity Upgrade Chain
```
COMMON → UNCOMMON → RARE → EPIC → LEGENDARY
```

---

## 13. Catalogue & Wishlist

**Router:** `GET/POST/DELETE /catalogue/*`

| Endpoint | Purpose |
|----------|---------|
| `GET /catalogue` | All item definitions sorted by category/rarity |
| `GET /catalogue/by-category` | Items grouped by category |
| `GET /catalogue/by-category/{cat}` | Single category |
| `POST /catalogue/{id}/wishlist` | Add item to wishlist (glows on drop) |
| `DELETE /catalogue/{id}/wishlist` | Remove from wishlist |

**Collection log:** `GET /collection` — all item definitions with discovery status and `first_seen_at`.

---

## 14. Feed & Journal

### Feed

**Router:** `GET /feed`

Recent notable events: activity drops, level-ups, achievements, streaks — aggregated activity stream.

### Player Journal

**Router:** `GET /player/journal`

Major milestones in chronological order (newest-first): level-ups, achievement unlocks, place unlocks.

### Suggestions

**Router:** `GET /suggestions`

Personalized activity nudges: streak danger warnings, gap-fill recommendations, challenge nudges, diversification prompts.

---

## 15. Database Schema Tables

| Table | Purpose |
|-------|---------|
| `sync_state` | Tracker API cursor and last sync timestamps |
| `player_profile` | Character identity, stats, mood, visual config, equipped items |
| `player_category_xp` | Per-category cumulative XP |
| `player_settings` | Daily XP target, goal difficulty scale |
| `streak_state` | Activity streak, login streak, longest streak, streak freeze charges |
| `item_definitions` | Item catalogue (rarity, category, effects, drop requirements) |
| `inventory` | Item instances (durability, tags, note, favorite, lock, expiry) |
| `reward_ledger` | Drop log (chunk_id + roll_n; unique for idempotency) |
| `places` | Place definitions (state, level, visit streak, connected places) |
| `place_slots` | Typed slots per place (occupant, accepts filter) |
| `place_perks` | Donated-item permanent XP boosts per place |
| `place_active_effects` | Rebuilt on slot change (xp_multiplier, set_bonus, category_xp_bonus) |
| `place_visit_log` | Visit timestamps per place |
| `place_invest_log` | Daily XP investment per place (enforces 500 XP/day cap) |
| `place_activity_log` | invest / donate / gift_item / visit audit trail |
| `slot_assignment_log` | Slot assign / remove audit trail |
| `crafting_log` | Upgrade / craft audit trail |
| `achievements` | Achievement definitions with condition type and threshold |
| `player_achievements` | Unlock timestamps per player |
| `pinned_achievements` | Up to 3 pinned achievements (display order) |
| `weekly_challenges` | Challenge definitions (metric, threshold, category) |
| `player_weekly_progress` | Per-week challenge progress and completion |
| `weekly_reroll_state` | Free reroll usage per ISO week |
| `daily_goals` | Auto-generated per-category daily targets |
| `challenge_events` | Time-windowed XP multiplier events |
| `trade_offers` | NPC exchange definitions |
| `chunk_log` | Processed activity chunk history |
| `collection_log` | First discovery timestamp per item |
| `wishlist` | Player wishlist (item glow on drop) |
| `skills` | Skill definitions (effect type, cost, max level) |
| `player_skills` | Unlock status and current level per player |
| `notification_prefs` | Per-event-type mute preferences |
| `pending_notifications` | Notification inbox (JSON payload, ack flag) |
