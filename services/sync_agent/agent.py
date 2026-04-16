from __future__ import annotations
import sqlite3
import uuid
from datetime import datetime, timezone
from enum import Enum
from services.contracts.chunk import Chunk
from services.models.enums import Category, PlaceState
from services.models.place import Place, PlaceItemPool
from services.models.item import ItemDefinition
from services.drop_engine.strategies import RollStrategy, SessionStrategy
from services.drop_engine.lottery import eligible_items, weighted_draw, DEFAULT_RARITY_WEIGHTS
from services.reward_ledger.ledger import record_drop, insert_level_up_notification, insert_place_unlock_notification
from services.progression.xp import award_category_xp, xp_for_chunk, get_total_xp, compute_level
from services.sync_agent.rate_limiter import RateLimiter
from services.sync_agent.tracker_client import TrackerClient
from services.place_service.service import list_places, check_unlock_condition
from services.place_service.effects import load_active_effects, compute_set_bonuses
from services.progression.streak import update_streak, get_streak
from services.progression.achievements import check_achievements
from services.progression.weekly_challenges import update_weekly_progress
from services.progression.daily_goals import ensure_daily_goals, update_daily_goal_progress
from services.notifications.desktop import notify_level_up
from services.progression.milestones import check_streak_milestone_drop
from services.place_service.upgrade import award_place_xp, get_active_place_ids

_STREAK_BONUS_THRESHOLD = 3
_STREAK_BONUS_FACTOR = 1.1


class PollResult(str, Enum):
    OK = "OK"
    ON_COOLDOWN = "ON_COOLDOWN"
    NO_NEW_CHUNKS = "NO_NEW_CHUNKS"


# _SENTINEL_PLACE is a shared module-level constant used when no place context is active.
# It must never be mutated — all consumers must treat it as read-only.
_SENTINEL_PLACE = Place(
    place_id="__global__", name="Global", place_type="global",
    item_pool=PlaceItemPool(),
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
            "UPDATE sync_state SET last_cursor=?, last_sync_at=? WHERE player_id='default'",
            (cursor, now),
        )
        self.db.commit()

    def _load_catalogue(self) -> list[ItemDefinition]:
        rows = self.db.execute("SELECT data FROM item_definitions").fetchall()
        result: list[ItemDefinition] = []
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

    @staticmethod
    def _aggregate_drop_mods(effects: list) -> dict[str, float]:
        """Fold drop_weight_mod effects into a {rarity_string: multiplier} dict.

        Multiple effects for the same rarity multiply together.
        """
        mods: dict[str, float] = {}
        for effect in effects:
            if effect.effect_type == "drop_weight_mod":
                rarity = effect.params.get("rarity", "")
                factor = float(effect.params.get("factor", 1.0))
                mods[rarity] = mods.get(rarity, 1.0) * factor
        return mods

    @staticmethod
    def _aggregate_xp_multiplier(effects: list) -> float:
        """Multiply all xp_multiplier and set_bonus effects together. Returns 1.0 if none."""
        multiplier = 1.0
        for effect in effects:
            if effect.effect_type in ("xp_multiplier", "set_bonus"):
                multiplier *= float(effect.params.get("factor", 1.0))
        return multiplier

    @staticmethod
    def _category_xp_bonus(effects: list, category: str) -> float:
        """Multiply all category_xp_bonus effects that match the given category.

        Returns 1.0 if no matching effects exist (i.e. no bonus).
        """
        multiplier = 1.0
        for effect in effects:
            if effect.effect_type == "category_xp_bonus":
                if effect.params.get("category", "").upper() == category.upper():
                    multiplier *= float(effect.params.get("factor", 1.0))
        return multiplier

    def _check_place_unlocks(self, player_level: int) -> None:
        """Unlock any LOCKED places whose condition is now met and notify the player."""
        places = list_places(self.db)
        newly_unlocked = False
        for place in places:
            if place.state != PlaceState.LOCKED:
                continue
            if check_unlock_condition(self.db, place, player_level):
                self.db.execute(
                    "UPDATE places SET state='UNLOCKED' WHERE place_id=?",
                    (place.place_id,),
                )
                insert_place_unlock_notification(
                    self.db, self.character_id, place.place_id, place.name
                )
                newly_unlocked = True
        if newly_unlocked:
            self.db.commit()

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
        current_level = compute_level(get_total_xp(self.db, self.character_id))
        active_effects = load_active_effects(self.db) + compute_set_bonuses(self.db)
        drop_mods = self._aggregate_drop_mods(active_effects)
        xp_multiplier = self._aggregate_xp_multiplier(active_effects)
        xp_earned_this_poll: dict[str, int] = {}

        streak = get_streak(self.db)
        if streak["current_streak"] >= _STREAK_BONUS_THRESHOLD:
            xp_multiplier *= _STREAK_BONUS_FACTOR

        for raw in chunk_dicts:
            try:
                chunk = Chunk.model_validate(raw)
            except Exception:
                continue

            if chunk.confidence < self.min_confidence:
                continue

            # Award XP for the activity itself; skip entire chunk if label is unknown
            try:
                cat = Category(chunk.label)
            except ValueError:
                continue  # unknown label — skip XP and drops

            cat_bonus = self._category_xp_bonus(active_effects, cat.value)
            xp = max(1, int(xp_for_chunk(chunk) * xp_multiplier * cat_bonus))
            xp_earned_this_poll[cat.value] = xp_earned_this_poll.get(cat.value, 0) + xp
            award_category_xp(
                self.db,
                character_id=self.character_id,
                category=cat,
                xp=xp,
            )
            self.db.execute(
                """
                INSERT OR IGNORE INTO chunk_log
                    (log_id, chunk_id, category, xp_awarded, duration_sec, processed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    chunk.chunk_id,
                    cat.value,
                    xp,
                    chunk.duration_sec,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            self.db.commit()

            # Award XP to any places that currently have items slotted
            for pid in get_active_place_ids(self.db):
                award_place_xp(self.db, pid, xp, self.character_id)
            self.db.commit()

            # Roll drops
            rolls = self.strategy.compute(chunk, luck)
            pool = eligible_items(catalogue, chunk, _SENTINEL_PLACE)

            for roll_n in range(rolls):
                winner = weighted_draw(pool, DEFAULT_RARITY_WEIGHTS, drop_weight_mods=drop_mods)
                if winner:
                    record_drop(
                        self.db,
                        chunk_id=chunk.chunk_id,
                        roll_n=roll_n,
                        item=winner,
                        character_id=self.character_id,
                    )

            # Level-up detection: includes XP from both the chunk and any drops
            new_level = compute_level(get_total_xp(self.db, self.character_id))
            if new_level > current_level:
                for lvl in range(current_level + 1, new_level + 1):
                    insert_level_up_notification(self.db, self.character_id, lvl)
                    notify_level_up(lvl)
                self.db.commit()
                self._check_place_unlocks(new_level)
                current_level = new_level

        if new_cursor:
            self._save_cursor(new_cursor)

        # Record activity for today's streak (UTC date of poll, not chunk date)
        update_streak(self.db, datetime.now(timezone.utc).date())
        streak = get_streak(self.db)
        check_streak_milestone_drop(self.db, self.character_id, streak["current_streak"])

        # Check and unlock any newly-met achievements
        check_achievements(self.db, self.character_id)

        # Update weekly challenge progress
        update_weekly_progress(self.db, self.character_id, xp_earned_this_poll)

        # Ensure today's daily goals exist, then credit progress for each chunk's category
        ensure_daily_goals(self.db, self.character_id)
        for raw in chunk_dicts:
            try:
                chunk = Chunk.model_validate(raw)
                cat = Category(chunk.label)
                update_daily_goal_progress(self.db, cat.value, chunk.duration_sec, self.character_id)
            except Exception:
                pass
        self.db.commit()

        return PollResult.OK

    def poll_with_summary(self, manual: bool = False) -> dict:
        """Like poll(), but returns a richer dict for the session-summary popup.

        Keys: result (str), total_xp (int), xp_by_category (dict),
              chunks_processed (int), drops_earned (int).
        """
        # Count drops before poll so we can diff after
        drops_before: int = self.db.execute(
            "SELECT COUNT(*) FROM reward_ledger WHERE character_id=?",
            (self.character_id,),
        ).fetchone()[0]

        # Run the normal poll
        result = self.poll(manual=manual)
        if result != PollResult.OK:
            return {"result": result.value, "total_xp": 0, "xp_by_category": {},
                    "chunks_processed": 0, "drops_earned": 0}

        # Count drops after poll
        drops_after: int = self.db.execute(
            "SELECT COUNT(*) FROM reward_ledger WHERE character_id=?",
            (self.character_id,),
        ).fetchone()[0]

        # Aggregate XP from chunk_log processed in this poll (since last cursor save,
        # approximate via latest processed_at — use chunk count as proxy)
        recent_rows = self.db.execute(
            """
            SELECT category, SUM(xp_awarded) AS xp, COUNT(*) AS cnt
            FROM chunk_log
            WHERE processed_at >= DATETIME('now', '-5 minutes')
            GROUP BY category
            """
        ).fetchall()
        xp_by_cat: dict[str, int] = {}
        chunks: int = 0
        for row in recent_rows:
            xp_by_cat[row["category"]] = row["xp"]
            chunks += row["cnt"]

        return {
            "result": result.value,
            "total_xp": sum(xp_by_cat.values()),
            "xp_by_category": xp_by_cat,
            "chunks_processed": chunks,
            "drops_earned": drops_after - drops_before,
        }
