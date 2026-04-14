from __future__ import annotations
import sqlite3
from contextlib import asynccontextmanager
from fastapi import FastAPI
from services.storage.db import get_db
from services.api.routers import sync, inventory, player, places, notifications


def create_app(db: sqlite3.Connection | None = None) -> FastAPI:
    """Factory so tests can inject an in-memory db."""
    _db: sqlite3.Connection | None = db

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal _db
        if _db is None:
            _db = get_db()
        app.state.db = _db
        yield
        if db is None:   # only close if we opened it
            _db.close()

    app = FastAPI(title="LLM Activity Game Services", version="0.1.0", lifespan=lifespan)

    if db is not None:
        # Pre-set for TestClient (lifespan also sets it, but this makes it available immediately)
        app.state.db = db

    app.include_router(sync.router, prefix="/sync", tags=["sync"])
    app.include_router(inventory.router, prefix="/inventory", tags=["inventory"])
    app.include_router(player.router, prefix="/player", tags=["player"])
    app.include_router(places.router, prefix="/places", tags=["places"])
    app.include_router(notifications.router, prefix="/notifications", tags=["notifications"])

    return app


app = create_app()
