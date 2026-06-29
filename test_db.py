import sqlite3
import tempfile
import os
from db import get_db, init_schema


def test_schema_creates_tables():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        conn = get_db({"DB_PATH": path})
        init_schema(conn)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "players" in tables
        assert "matches" in tables
        assert "predictions" in tables
    finally:
        os.unlink(path)
