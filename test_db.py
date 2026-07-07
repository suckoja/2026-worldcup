import sqlite3
import tempfile
import os
from db import get_db, init_schema
import db as dbmod


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


def _fresh_conn():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    path = f.name
    f.close()
    conn = get_db({"DB_PATH": path})
    init_schema(conn)
    return conn, path


def test_schema_adds_doubled_column():
    conn, path = _fresh_conn()
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(predictions)").fetchall()]
        assert "doubled" in cols
    finally:
        conn.close()
        os.unlink(path)


def _seed_match(conn, round_val="16"):
    conn.execute("""
        INSERT INTO matches
        (match_date_ict, kickoff_utc, deadline_ict, home_team_en, away_team_en, round)
        VALUES ('2026-07-08', '2026-07-08T16:00:00Z', '2026-07-07T15:00:00', 'Argentina', 'Egypt', ?)
    """, (round_val,))
    conn.commit()
    return conn.execute(
        "SELECT id FROM matches WHERE home_team_en = 'Argentina' AND away_team_en = 'Egypt'"
    ).fetchone()["id"]


def _seed_player(conn, name="Kritsana Th."):
    dbmod.upsert_player(conn, name)
    return dbmod.get_player_id(conn, name)


def test_get_prediction_returns_none_when_missing():
    conn, path = _fresh_conn()
    try:
        match_id = _seed_match(conn)
        player_id = _seed_player(conn)
        assert dbmod.get_prediction(conn, player_id, match_id) is None
    finally:
        conn.close()
        os.unlink(path)


def test_set_doubled_and_count_in_round():
    conn, path = _fresh_conn()
    try:
        match_id = _seed_match(conn, round_val="16")
        player_id = _seed_player(conn)
        dbmod.upsert_prediction(conn, player_id, match_id, 2, 1, None, "2026-07-07T10:00:00")
        pred = dbmod.get_prediction(conn, player_id, match_id)
        assert pred["doubled"] == 0

        dbmod.set_doubled(conn, pred["id"], 1)
        pred = dbmod.get_prediction(conn, player_id, match_id)
        assert pred["doubled"] == 1
        assert dbmod.count_doubled_in_round(conn, player_id, "16") == 1

        dbmod.set_doubled(conn, pred["id"], 0)
        assert dbmod.count_doubled_in_round(conn, player_id, "16") == 0
    finally:
        conn.close()
        os.unlink(path)


def test_has_doubled_in_round():
    conn, path = _fresh_conn()
    try:
        match_id = _seed_match(conn, round_val="16")
        player_id = _seed_player(conn, "Kritsana Th.")
        dbmod.upsert_prediction(conn, player_id, match_id, 2, 1, None, "2026-07-07T10:00:00")
        pred = dbmod.get_prediction(conn, player_id, match_id)
        dbmod.set_doubled(conn, pred["id"], 1)

        names = dbmod.has_doubled_in_round(conn, "16")
        assert names == {"Kritsana Th."}
        assert dbmod.has_doubled_in_round(conn, "8") == set()
    finally:
        conn.close()
        os.unlink(path)


def test_get_current_round_prefers_earliest_unplayed():
    conn, path = _fresh_conn()
    try:
        conn.execute("""
            INSERT INTO matches
            (match_date_ict, kickoff_utc, deadline_ict, home_team_en, away_team_en, round, home_score, away_score)
            VALUES ('2026-07-04', '2026-07-04T16:00:00Z', '2026-07-03T15:00:00', 'France', 'Sweden', '32', 3, 0)
        """)
        conn.execute("""
            INSERT INTO matches
            (match_date_ict, kickoff_utc, deadline_ict, home_team_en, away_team_en, round)
            VALUES ('2026-07-08', '2026-07-08T16:00:00Z', '2026-07-07T15:00:00', 'Argentina', 'Egypt', '16')
        """)
        conn.commit()
        assert dbmod.get_current_round(conn) == "16"
    finally:
        conn.close()
        os.unlink(path)
