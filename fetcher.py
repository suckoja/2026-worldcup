from __future__ import annotations

import sqlite3
import requests

API_TEAM_MAP = {
    "Brazil": "Brazil",
    "Japan": "Japan",
    "Germany": "Germany",
    "Paraguay": "Paraguay",
    "Netherlands": "Netherlands",
    "Morocco": "Morocco",
    "South Africa": "South Africa",
    "Canada": "Canada",
    "Norway": "Norway",
    "Côte d'Ivoire": "Ivory Coast",
    "Ivory Coast": "Ivory Coast",
    "France": "France",
    "Sweden": "Sweden",
    "Mexico": "Mexico",
    "Ecuador": "Ecuador",
    "England": "England",
    "Congo DR": "Congo DR",
    "DR Congo": "Congo DR",
    "USA": "USA",
    "United States": "USA",
    "Bosnia and Herzegovina": "Bosnia",
    "Belgium": "Belgium",
    "Spain": "Spain",
    "Austria": "Austria",
    "Portugal": "Portugal",
    "Croatia": "Croatia",
    "Switzerland": "Switzerland",
    "Algeria": "Algeria",
    "Australia": "Australia",
    "Egypt": "Egypt",
    "Argentina": "Argentina",
    "Cabo Verde": "Cape Verde",
    "Cape Verde": "Cape Verde",
    "Colombia": "Colombia",
    "Ghana": "Ghana",
}


def sync_results(conn: sqlite3.Connection, api_key: str) -> list:
    """Fetch finished WC matches, update DB, return list of result strings."""
    resp = requests.get(
        "https://api.football-data.org/v4/competitions/WC/matches",
        headers={"X-Auth-Token": api_key},
        params={"status": "FINISHED"},
        timeout=10
    )
    resp.raise_for_status()
    data = resp.json()

    updated = []
    needs_manual = []
    for match in data.get("matches", []):
        home_api = match["homeTeam"]["name"]
        away_api = match["awayTeam"]["name"]
        home_en = API_TEAM_MAP.get(home_api)
        away_en = API_TEAM_MAP.get(away_api)
        if not home_en or not away_en:
            continue

        score = match.get("score", {})
        duration = score.get("duration", "REGULAR")

        if duration in ("EXTRA_TIME", "PENALTY_SHOOTOUT"):
            needs_manual.append(f"{home_en} vs {away_en}")
            continue

        ft = score.get("fullTime", {})
        home_score = ft.get("home")
        away_score = ft.get("away")
        if home_score is None or away_score is None:
            continue

        result = conn.execute("""
            UPDATE matches SET home_score = ?, away_score = ?
            WHERE home_team_en = ? AND away_team_en = ?
              AND (home_score IS NULL OR home_score != ? OR away_score != ?)
        """, (home_score, away_score, home_en, away_en, home_score, away_score))

        if result.rowcount > 0:
            updated.append(f"{home_en} {home_score}-{away_score} {away_en}")

    conn.commit()
    return updated, needs_manual
