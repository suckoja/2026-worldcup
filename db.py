from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Optional

ICT = timezone(timedelta(hours=7))


def get_db(config: dict) -> sqlite3.Connection:
    conn = sqlite3.connect(config["DB_PATH"])
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY,
            line_display_name TEXT UNIQUE NOT NULL,
            aliases TEXT NOT NULL DEFAULT '[]'
        );

        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY,
            match_date_ict TEXT NOT NULL,
            kickoff_utc TEXT NOT NULL,
            deadline_ict TEXT NOT NULL,
            home_team_en TEXT NOT NULL,
            away_team_en TEXT NOT NULL,
            home_team_th TEXT,
            away_team_th TEXT,
            home_score INTEGER,
            away_score INTEGER,
            round TEXT NOT NULL DEFAULT '32'
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_matches_unique
            ON matches(home_team_en, away_team_en, round);

        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY,
            player_id INTEGER NOT NULL REFERENCES players(id),
            match_id INTEGER NOT NULL REFERENCES matches(id),
            home_pred INTEGER NOT NULL,
            away_pred INTEGER NOT NULL,
            line_message_id TEXT,
            submitted_at TEXT NOT NULL,
            points INTEGER,
            UNIQUE(player_id, match_id)
        );
    """)
    conn.commit()
    _ensure_column(conn, "predictions", "doubled", "INTEGER NOT NULL DEFAULT 0")


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, coldef: str):
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coldef}")
        conn.commit()


def now_ict() -> str:
    return datetime.now(ICT).strftime("%Y-%m-%dT%H:%M:%S")


def today_ict() -> str:
    return datetime.now(ICT).strftime("%Y-%m-%d")


def load_players(path: str = "players.json") -> list:
    return json.load(open(path, encoding="utf-8"))


def resolve_player(name: str, players: list) -> tuple:
    """
    Returns (line_display_name, []) on unique match.
    Returns (None, [candidates]) on ambiguous.
    Returns (None, []) on no match.
    """
    name_lower = name.lower().strip()
    matches = []
    for p in players:
        if p["line_display_name"].lower() == name_lower:
            return (p["line_display_name"], [])
        aliases = [a.lower() for a in p.get("aliases", [])]
        if name_lower in aliases or name_lower in p["line_display_name"].lower():
            matches.append(p["line_display_name"])
    if len(matches) == 1:
        return (matches[0], [])
    if len(matches) > 1:
        return (None, matches)
    return (None, [])


def upsert_player(conn: sqlite3.Connection, line_display_name: str, aliases: Optional[list] = None):
    conn.execute(
        "INSERT OR IGNORE INTO players (line_display_name, aliases) VALUES (?, ?)",
        (line_display_name, json.dumps(aliases or []))
    )
    conn.commit()


def get_player_id(conn: sqlite3.Connection, line_display_name: str) -> Optional[int]:
    row = conn.execute(
        "SELECT id FROM players WHERE line_display_name = ?", (line_display_name,)
    ).fetchone()
    return row["id"] if row else None


def get_match_by_teams(conn: sqlite3.Connection, home_en: str, away_en: str) -> Optional[sqlite3.Row]:
    return conn.execute("""
        SELECT * FROM matches
        WHERE (home_team_en = ? AND away_team_en = ?)
           OR (home_team_en = ? AND away_team_en = ?)
    """, (home_en, away_en, away_en, home_en)).fetchone()


def get_match_by_id(conn: sqlite3.Connection, match_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()


def upsert_prediction(conn: sqlite3.Connection, player_id: int, match_id: int,
                      home_pred: int, away_pred: int, line_message_id: Optional[str],
                      submitted_at: str):
    conn.execute("""
        INSERT INTO predictions (player_id, match_id, home_pred, away_pred, line_message_id, submitted_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(player_id, match_id) DO UPDATE SET
            home_pred = excluded.home_pred,
            away_pred = excluded.away_pred,
            line_message_id = excluded.line_message_id,
            submitted_at = excluded.submitted_at,
            points = NULL
    """, (player_id, match_id, home_pred, away_pred, line_message_id, submitted_at))
    conn.commit()


def delete_prediction_by_message_id(conn: sqlite3.Connection, message_id: str) -> bool:
    """Delete prediction if match has not kicked off. Returns True if deleted."""
    row = conn.execute("""
        SELECT p.id, m.kickoff_utc FROM predictions p
        JOIN matches m ON p.match_id = m.id
        WHERE p.line_message_id = ?
    """, (message_id,)).fetchone()
    if not row:
        return False
    kickoff_utc = datetime.fromisoformat(row["kickoff_utc"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) >= kickoff_utc:
        return False
    conn.execute("DELETE FROM predictions WHERE id = ?", (row["id"],))
    conn.commit()
    return True


def get_standings(conn: sqlite3.Connection) -> list:
    return conn.execute("""
        SELECT p.line_display_name,
               COALESCE(SUM(pr.points), 0) AS total_points,
               COUNT(pr.id) AS matches_played
        FROM players p
        LEFT JOIN predictions pr ON p.id = pr.player_id
        GROUP BY p.id
        ORDER BY total_points DESC, p.line_display_name
    """).fetchall()


def get_player_history(conn: sqlite3.Connection, player_id: int) -> list:
    return conn.execute("""
        SELECT m.match_date_ict, m.home_team_th, m.away_team_th,
               m.home_team_en, m.away_team_en,
               m.home_score, m.away_score,
               pr.home_pred, pr.away_pred, pr.points
        FROM predictions pr
        JOIN matches m ON pr.match_id = m.id
        WHERE pr.player_id = ?
        ORDER BY m.kickoff_utc
    """, (player_id,)).fetchall()


def get_today_predictions(conn: sqlite3.Connection, date_ict: str) -> list:
    return conn.execute("""
        SELECT m.home_team_th, m.away_team_th, m.home_team_en, m.away_team_en,
               m.home_score, m.away_score, m.kickoff_utc,
               p.line_display_name,
               pr.home_pred, pr.away_pred, pr.points
        FROM matches m
        LEFT JOIN predictions pr ON m.id = pr.match_id
        LEFT JOIN players p ON pr.player_id = p.id
        WHERE m.match_date_ict = ?
        ORDER BY m.kickoff_utc, p.line_display_name
    """, (date_ict,)).fetchall()


def get_prediction(conn: sqlite3.Connection, player_id: int, match_id: int) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM predictions WHERE player_id = ? AND match_id = ?",
        (player_id, match_id)
    ).fetchone()


def set_doubled(conn: sqlite3.Connection, prediction_id: int, value: int):
    conn.execute("UPDATE predictions SET doubled = ? WHERE id = ?", (value, prediction_id))
    conn.commit()


def count_doubled_in_round(conn: sqlite3.Connection, player_id: int, round_val: str) -> int:
    row = conn.execute("""
        SELECT COUNT(*) AS n FROM predictions pr
        JOIN matches m ON pr.match_id = m.id
        WHERE pr.player_id = ? AND pr.doubled = 1 AND m.round = ?
    """, (player_id, round_val)).fetchone()
    return row["n"]


def has_doubled_in_round(conn: sqlite3.Connection, round_val: str) -> set:
    rows = conn.execute("""
        SELECT DISTINCT p.line_display_name
        FROM predictions pr
        JOIN players p ON pr.player_id = p.id
        JOIN matches m ON pr.match_id = m.id
        WHERE pr.doubled = 1 AND m.round = ?
    """, (round_val,)).fetchall()
    return {r["line_display_name"] for r in rows}


def get_current_round(conn: sqlite3.Connection) -> Optional[str]:
    row = conn.execute(
        "SELECT round FROM matches WHERE home_score IS NULL ORDER BY kickoff_utc LIMIT 1"
    ).fetchone()
    if row:
        return row["round"]
    row = conn.execute(
        "SELECT round FROM matches ORDER BY kickoff_utc DESC LIMIT 1"
    ).fetchone()
    return row["round"] if row else None
