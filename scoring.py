from __future__ import annotations

import sqlite3


def _result(h: int, a: int) -> int:
    """1 = home win, 0 = draw, -1 = away win."""
    return (h > a) - (h < a)


def score_prediction(
    predicted: tuple,
    actual: tuple,
    round: str,
    rules: dict
) -> int:
    r = rules[round]
    if predicted == actual:
        return r["exact"]
    if _result(*predicted) == _result(*actual):
        return r["correct"]
    return r["wrong"]


def recalculate_all(conn: sqlite3.Connection, rules: dict):
    """Recalculate points for all predictions where match result is known."""
    rows = conn.execute("""
        SELECT p.id, p.home_pred, p.away_pred,
               m.home_score, m.away_score, m.round
        FROM predictions p
        JOIN matches m ON p.match_id = m.id
        WHERE m.home_score IS NOT NULL AND m.away_score IS NOT NULL
    """).fetchall()

    for row in rows:
        pts = score_prediction(
            (row["home_pred"], row["away_pred"]),
            (row["home_score"], row["away_score"]),
            row["round"],
            rules
        )
        conn.execute("UPDATE predictions SET points = ? WHERE id = ?", (pts, row["id"]))

    conn.commit()
