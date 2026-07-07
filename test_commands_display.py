import os
import tempfile

import db
import commands

RULES = {
    "32":    {"exact": 2, "correct": 1, "wrong": 0, "double_cap": 0},
    "16":    {"exact": 4, "correct": 2, "wrong": 0, "double_cap": 2},
    "8":     {"exact": 6, "correct": 3, "wrong": 0, "double_cap": 1},
    "4":     {"exact": 8, "correct": 4, "wrong": 0, "double_cap": 1},
    "final": {"exact": 8, "correct": 4, "wrong": 0, "double_cap": 0},
}


def _setup():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    path = f.name
    f.close()
    conn = db.get_db({"DB_PATH": path})
    db.init_schema(conn)
    conn.execute("""
        INSERT INTO matches
        (match_date_ict, kickoff_utc, deadline_ict, home_team_en, away_team_en,
         home_team_th, away_team_th, round)
        VALUES ('2026-07-08', '2026-07-08T16:00:00Z', '2099-01-01T00:00:00', 'Argentina', 'Egypt',
                'อาร์เจนตินา', 'อียิปต์', '16')
    """)
    conn.commit()
    db.upsert_player(conn, "Kritsana Th.")
    player_id = db.get_player_id(conn, "Kritsana Th.")
    match_row = db.get_match_by_teams(conn, "Argentina", "Egypt")
    db.upsert_prediction(conn, player_id, match_row["id"], 2, 1, None, "2026-07-07T10:00:00")
    pred = db.get_prediction(conn, player_id, match_row["id"])
    db.set_doubled(conn, pred["id"], 1)
    return conn, path


def test_result_shows_double_marker():
    conn, path = _setup()
    try:
        player_id = db.get_player_id(conn, "Kritsana Th.")
        text = commands._result_player_text(conn, player_id, "Kritsana Th.")
        assert "🔥x2" in text
    finally:
        conn.close()
        os.unlink(path)


def test_stand_shows_flame_for_current_round():
    conn, path = _setup()
    try:
        text = commands._standings_text(conn)
        assert "🔥" in text
        assert "ใช้ double ในรอบนี้แล้ว" in text
    finally:
        conn.close()
        os.unlink(path)
