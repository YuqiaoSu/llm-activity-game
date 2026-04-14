from __future__ import annotations
import sqlite3
from datetime import datetime, timezone
from enum import Enum
from services.contracts.chunk import Chunk
from services.models.enums import Category
from services.models.place import Place, PlaceItemPool
from services.drop_engine.strategies import RollStrategy, SessionStrategy
from services.drop_engine.lottery import eligible_items, weighted_draw, DEFAULT_RARITY_WEIGHTS
from services.reward_ledger.ledger import record_drop
from services.progression.xp import award_category_xp, xp_for_chunk
from services.sync_agent.rate_limiter import RateLimiter
from services.sync_agent.tracker_client import TrackerClient
from services.models.item import ItemDefinition


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

            # Award XP for the activity itself; skip entire chunk if label is unknown
            try:
                cat = Category(chunk.label)
            except ValueError:
                continue  # unknown label — skip XP and drops

            award_category_xp(
                self.db,
                character_id=self.character_id,
                category=cat,
                xp=xp_for_chunk(chunk),
            )
            self.db.commit()

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
