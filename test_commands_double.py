import os
import tempfile
from datetime import datetime, timezone, timedelta

import db
import commands

ICT = timezone(timedelta(hours=7))

RULES = {
    "32":    {"exact": 2, "correct": 1, "wrong": 0, "double_cap": 0},
    "16":    {"exact": 4, "correct": 2, "wrong": 0, "double_cap": 2},
    "8":     {"exact": 6, "correct": 3, "wrong": 0, "double_cap": 1},
    "4":     {"exact": 8, "correct": 4, "wrong": 0, "double_cap": 1},
    "final": {"exact": 8, "correct": 4, "wrong": 0, "double_cap": 0},
}

CONFIG = {"ADMIN_LINE_USER_ID": "Uadmin"}
PLAYERS = [{"line_display_name": "Kritsana Th.", "aliases": ["kritsana", "นา"]}]
TEAMS = {"อาร์เจนตินา": "Argentina", "อียิปต์": "Egypt", "Argentina": "Argentina", "Egypt": "Egypt"}


def _setup(round_val="16", kickoff_passed=False):
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    path = f.name
    f.close()
    conn = db.get_db({"DB_PATH": path})
    db.init_schema(conn)
    # deadline_ict always in the past — /double no longer checks it, only kickoff_utc matters
    kickoff = (datetime.now(timezone.utc) - timedelta(hours=1)) if kickoff_passed else (datetime.now(timezone.utc) + timedelta(hours=1))
    conn.execute("""
        INSERT INTO matches
        (match_date_ict, kickoff_utc, deadline_ict, home_team_en, away_team_en,
         home_team_th, away_team_th, round)
        VALUES ('2026-07-08', ?, '2020-01-01T00:00:00', 'Argentina', 'Egypt',
                'อาร์เจนตินา', 'อียิปต์', ?)
    """, (kickoff.strftime("%Y-%m-%dT%H:%M:%SZ"), round_val))
    conn.commit()
    db.upsert_player(conn, "Kritsana Th.")
    player_id = db.get_player_id(conn, "Kritsana Th.")
    match_row = db.get_match_by_teams(conn, "Argentina", "Egypt")
    db.upsert_prediction(conn, player_id, match_row["id"], 2, 1, None, "2026-07-07T10:00:00")
    return conn, path


def test_double_activates_and_reports_quota():
    conn, path = _setup(round_val="16")
    try:
        resp = commands.handle_command(
            "/double kritsana อาร์เจนตินา อียิปต์", "Uadmin", conn, CONFIG, PLAYERS, RULES, TEAMS
        )
        assert "🔥" in resp
        assert "1/2" in resp
        player_id = db.get_player_id(conn, "Kritsana Th.")
        assert db.count_doubled_in_round(conn, player_id, "16") == 1
    finally:
        conn.close()
        os.unlink(path)


def test_double_toggles_off_on_second_call():
    conn, path = _setup(round_val="16")
    try:
        commands.handle_command(
            "/double kritsana อาร์เจนตินา อียิปต์", "Uadmin", conn, CONFIG, PLAYERS, RULES, TEAMS
        )
        resp = commands.handle_command(
            "/double kritsana อาร์เจนตินา อียิปต์", "Uadmin", conn, CONFIG, PLAYERS, RULES, TEAMS
        )
        assert "ยกเลิก" in resp
        player_id = db.get_player_id(conn, "Kritsana Th.")
        assert db.count_doubled_in_round(conn, player_id, "16") == 0
    finally:
        conn.close()
        os.unlink(path)


def test_double_rejects_when_no_prediction():
    conn, path = _setup(round_val="16")
    try:
        db.upsert_player(conn, "Other Player")
        resp = commands.handle_command(
            "/double other อาร์เจนตินา อียิปต์", "Uadmin", conn, CONFIG,
            PLAYERS + [{"line_display_name": "Other Player", "aliases": ["other"]}], RULES, TEAMS
        )
        assert "ยังไม่ได้ทาย" in resp
    finally:
        conn.close()
        os.unlink(path)


def test_double_rejects_after_kickoff():
    conn, path = _setup(round_val="16", kickoff_passed=True)
    try:
        resp = commands.handle_command(
            "/double kritsana อาร์เจนตินา อียิปต์", "Uadmin", conn, CONFIG, PLAYERS, RULES, TEAMS
        )
        assert "เริ่มแล้ว" in resp
    finally:
        conn.close()
        os.unlink(path)


def test_double_allowed_after_prediction_deadline_but_before_kickoff():
    # deadline_ict is always in the past in _setup; this confirms /double
    # still works as long as kickoff hasn't happened yet.
    conn, path = _setup(round_val="16", kickoff_passed=False)
    try:
        resp = commands.handle_command(
            "/double kritsana อาร์เจนตินา อียิปต์", "Uadmin", conn, CONFIG, PLAYERS, RULES, TEAMS
        )
        assert "🔥" in resp
    finally:
        conn.close()
        os.unlink(path)


def test_double_rejects_at_cap():
    conn, path = _setup(round_val="8")  # double_cap = 1
    try:
        commands.handle_command(
            "/double kritsana อาร์เจนตินา อียิปต์", "Uadmin", conn, CONFIG, PLAYERS, RULES, TEAMS
        )
        # toggled on, now toggle off then simulate already-used-cap by re-flagging manually
        player_id = db.get_player_id(conn, "Kritsana Th.")
        match_row = db.get_match_by_teams(conn, "Argentina", "Egypt")
        pred = db.get_prediction(conn, player_id, match_row["id"])
        db.set_doubled(conn, pred["id"], 1)  # ensure it's on
        # Add a second match in same round already doubled to hit cap before this one's toggle-off path
        conn.execute("""
            INSERT INTO matches
            (match_date_ict, kickoff_utc, deadline_ict, home_team_en, away_team_en,
             home_team_th, away_team_th, round)
            VALUES ('2026-07-09', '2026-07-09T16:00:00Z', '2099-01-01T00:00:00', 'Switzerland', 'Colombia',
                    'สวิตเซอร์แลนด์', 'โคลอมเบีย', '8')
        """)
        conn.commit()
        match2 = db.get_match_by_teams(conn, "Switzerland", "Colombia")
        db.upsert_prediction(conn, player_id, match2["id"], 1, 1, None, "2026-07-07T10:00:00")
        teams2 = dict(TEAMS, **{"สวิตเซอร์แลนด์": "Switzerland", "โคลอมเบีย": "Colombia"})
        resp = commands.handle_command(
            "/double kritsana สวิตเซอร์แลนด์ โคลอมเบีย", "Uadmin", conn, CONFIG, PLAYERS, RULES, teams2
        )
        assert "ครบโควต้า" in resp
    finally:
        conn.close()
        os.unlink(path)


def test_double_non_admin_ignored():
    conn, path = _setup(round_val="16")
    try:
        resp = commands.handle_command(
            "/double kritsana อาร์เจนตินา อียิปต์", "Usomeoneelse", conn, CONFIG, PLAYERS, RULES, TEAMS
        )
        assert resp is None
    finally:
        conn.close()
        os.unlink(path)
