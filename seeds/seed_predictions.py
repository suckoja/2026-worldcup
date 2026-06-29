#!/usr/bin/env python3
"""Bulk seed past predictions. Edit PREDICTIONS list and run."""
from __future__ import annotations
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import db
import scoring

# (player_alias, home_pred, away_pred, home_en, away_en, date_ict)
PREDICTIONS = [
    # Match 1: South Africa vs Canada (2026-06-28) — actual 0-1 Canada
    ("thomas",    0, 2, "South Africa", "Canada", "2026-06-28"),
    ("kritsana",  1, 2, "South Africa", "Canada", "2026-06-28"),
    ("momo",      0, 1, "South Africa", "Canada", "2026-06-28"),
    ("trisit",    0, 0, "South Africa", "Canada", "2026-06-28"),
    ("benz",      0, 1, "South Africa", "Canada", "2026-06-28"),
    ("wattana",   1, 3, "South Africa", "Canada", "2026-06-28"),
    ("aob",       1, 2, "South Africa", "Canada", "2026-06-28"),
    ("jirawut",   0, 2, "South Africa", "Canada", "2026-06-28"),
    ("pj",        0, 3, "South Africa", "Canada", "2026-06-28"),
    ("เอ",        0, 1, "South Africa", "Canada", "2026-06-28"),
    ("trinity",   1, 1, "South Africa", "Canada", "2026-06-28"),
    ("chaiwat",   1, 3, "South Africa", "Canada", "2026-06-28"),
    ("supagorn",  0, 2, "South Africa", "Canada", "2026-06-28"),
    ("kwang",     1, 2, "South Africa", "Canada", "2026-06-28"),
    ("sirichai",  0, 2, "South Africa", "Canada", "2026-06-28"),
    ("piyaporn",  1, 2, "South Africa", "Canada", "2026-06-28"),
    ("art",       1, 2, "South Africa", "Canada", "2026-06-28"),
    # Ryu42 and Tae did not submit for Match 1
]


def main():
    config = json.load(open("config.json"))
    players_data = json.load(open("players.json", encoding="utf-8"))
    rules = json.load(open("scoring_rules.json"))
    conn = db.get_db(config)

    # Ensure all players exist in DB
    for p in players_data:
        db.upsert_player(conn, p["line_display_name"], p.get("aliases", []))

    ok = 0
    for (alias, home_pred, away_pred, home_en, away_en, date) in PREDICTIONS:
        name, candidates = db.resolve_player(alias, players_data)
        if not name:
            print(f"SKIP: player not found for alias '{alias}'")
            continue

        match_row = db.get_match_by_teams(conn, home_en, away_en)
        if not match_row:
            print(f"SKIP: match not found {home_en} vs {away_en}")
            continue

        player_id = db.get_player_id(conn, name)
        db.upsert_prediction(conn, player_id, match_row["id"],
                             home_pred, away_pred, None, f"{date}T00:00:00")
        print(f"OK: {name:<25} {home_en} {home_pred}-{away_pred} {away_en}")
        ok += 1

    # Seed actual result for Match 1
    conn.execute(
        "UPDATE matches SET home_score=0, away_score=1 "
        "WHERE home_team_en='South Africa' AND away_team_en='Canada'"
    )
    conn.commit()
    print(f"\nResult seeded: South Africa 0-1 Canada")

    scoring.recalculate_all(conn, rules)
    print("Points recalculated.")
    print(f"\nSeeded {ok} predictions.")

    # Print standings for verification
    rows = db.get_standings(conn)
    print("\n=== Standings ===")
    rank = 1
    prev_pts = None
    for i, row in enumerate(rows):
        pts = row["total_points"]
        if pts != prev_pts:
            rank = i + 1
            prev_pts = pts
        print(f"{rank:2}. {row['line_display_name']:<25} {pts} pts")


if __name__ == "__main__":
    main()
