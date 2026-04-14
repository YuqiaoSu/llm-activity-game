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
