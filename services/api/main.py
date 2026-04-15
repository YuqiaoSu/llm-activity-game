from __future__ import annotations
import asyncio
import logging
import os
import sqlite3
from contextlib import asynccontextmanager
from fastapi import FastAPI
from services.storage.db import get_db
from services.api.routers import sync, inventory, player, places, notifications, stats, history
from services.sync_agent.agent import SyncAgent
from services.sync_agent.tracker_client import TrackerClient
from services.sync_agent.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

_BACKGROUND_POLL_INTERVAL_SEC = int(os.environ.get("POLL_INTERVAL_SEC", "300"))  # 5 min default


async def _background_poll_loop(app: FastAPI) -> None:
    """Periodically poll the tracker and process new chunks."""
    while True:
        await asyncio.sleep(_BACKGROUND_POLL_INTERVAL_SEC)
        try:
            result = app.state.sync_agent.poll(manual=False)
            logger.info("Background poll: %s", result.value)
        except Exception:
            logger.exception("Background poll failed")


def create_app(db: sqlite3.Connection | None = None) -> FastAPI:
    """Factory so tests can inject an in-memory db."""
    _db: sqlite3.Connection | None = db

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal _db
        if _db is None:
            _db = get_db()
        app.state.db = _db
        app.state.sync_agent = SyncAgent(
            db=_db,
            tracker_client=TrackerClient(),
            character_id="player_default",
            rate_limiter=RateLimiter(cooldown_sec=60),
        )
        task = asyncio.create_task(_background_poll_loop(app))
        yield
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        if db is None:   # only close if we opened it
            _db.close()

    app = FastAPI(title="LLM Activity Game Services", version="0.1.0", lifespan=lifespan)

    if db is not None:
        # Pre-set for TestClient (lifespan also sets it, but this makes it available immediately)
        app.state.db = db
        app.state.sync_agent = SyncAgent(
            db=db,
            tracker_client=TrackerClient(),
            character_id="player_default",
            rate_limiter=RateLimiter(cooldown_sec=60),
        )

    app.include_router(sync.router, prefix="/sync", tags=["sync"])
    app.include_router(inventory.router, prefix="/inventory", tags=["inventory"])
    app.include_router(player.router, prefix="/player", tags=["player"])
    app.include_router(places.router, prefix="/places", tags=["places"])
    app.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
    app.include_router(stats.router, prefix="/stats", tags=["stats"])
    app.include_router(history.router, prefix="/history", tags=["history"])

    return app


app = create_app()
