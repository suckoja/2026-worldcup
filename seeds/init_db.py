#!/usr/bin/env python3
"""Run once to create DB schema and seed match schedule."""
from __future__ import annotations
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import get_db, init_schema

# (match_date_ict, kickoff_utc, deadline_ict, home_en, away_en, home_th, away_th, round)
MATCHES = [
    ("2026-06-28", "2026-06-28T16:00:00Z", "2026-06-28T08:00:00Z", "South Africa", "Canada",      "แอฟริกาใต้",       "แคนาดา",       "32"),
    ("2026-06-30", "2026-06-29T17:00:00Z", "2026-06-29T08:00:00Z", "Brazil",        "Japan",       "บราซิล",          "ญี่ปุ่น",        "32"),
    ("2026-06-30", "2026-06-29T20:30:00Z", "2026-06-29T08:00:00Z", "Germany",       "Paraguay",    "เยอรมัน",         "ปารากวัย",      "32"),
    ("2026-06-30", "2026-06-30T01:00:00Z", "2026-06-29T08:00:00Z", "Netherlands",   "Morocco",     "เนเธอร์แลนด์",    "โมร็อกโก",      "32"),
    ("2026-07-01", "2026-06-30T17:00:00Z", "2026-06-30T08:00:00Z", "Ivory Coast",   "Norway",      "ไอวอรีโคสต์",     "นอร์เวย์",      "32"),
    ("2026-07-01", "2026-06-30T21:00:00Z", "2026-06-30T08:00:00Z", "France",        "Sweden",      "ฝรั่งเศส",        "สวีเดน",        "32"),
    ("2026-07-01", "2026-07-01T01:00:00Z", "2026-06-30T08:00:00Z", "Mexico",        "Ecuador",     "เม็กซิโก",        "เอกวาดอร์",     "32"),
    ("2026-07-02", "2026-07-01T16:00:00Z", "2026-07-01T08:00:00Z", "England",       "Congo DR",    "อังกฤษ",          "คองโก",        "32"),
    ("2026-07-02", "2026-07-01T20:00:00Z", "2026-07-01T08:00:00Z", "Belgium",       "Senegal",     "เบลเยียม",        "เซเนกัล",      "32"),
    ("2026-07-02", "2026-07-02T00:00:00Z", "2026-07-01T08:00:00Z", "USA",           "Bosnia",      "สหรัฐ",           "บอสเนีย",       "32"),
    ("2026-07-03", "2026-07-02T19:00:00Z", "2026-07-02T08:00:00Z", "Spain",         "Austria",     "สเปน",            "ออสเตรีย",      "32"),
    ("2026-07-03", "2026-07-02T23:00:00Z", "2026-07-02T08:00:00Z", "Portugal",      "Croatia",     "โปรตุเกส",        "โครเอเชีย",     "32"),
    ("2026-07-03", "2026-07-03T03:00:00Z", "2026-07-02T08:00:00Z", "Switzerland",   "Algeria",     "สวิตเซอร์แลนด์",  "แอลจีเรีย",    "32"),
    ("2026-07-04", "2026-07-03T18:00:00Z", "2026-07-03T08:00:00Z", "Australia",     "Egypt",       "ออสเตรเลีย",      "อียิปต์",       "32"),
    ("2026-07-04", "2026-07-03T22:00:00Z", "2026-07-03T08:00:00Z", "Argentina",     "Cape Verde",  "อาร์เจนตินา",     "เคปเวิร์ด",     "32"),
    ("2026-07-04", "2026-07-04T01:30:00Z", "2026-07-03T08:00:00Z", "Colombia",      "Ghana",       "โคลอมเบีย",       "กานา",         "32"),

    # Round of 16 — official FIFA bracket, 6/8 slots known (Argentina/CapeVerde-Australia/Egypt
    # and Switzerland/Algeria-Colombia/Ghana winners TBD pending tonight's R32 results)
    ("2026-07-05", "2026-07-04T17:00:00Z", "2026-07-04T08:00:00Z", "Canada",        "Morocco",     "แคนาดา",          "โมร็อกโก",     "16"),
    ("2026-07-05", "2026-07-04T21:00:00Z", "2026-07-04T08:00:00Z", "Paraguay",      "France",      "ปารากวัย",        "ฝรั่งเศส",      "16"),
    ("2026-07-06", "2026-07-05T20:00:00Z", "2026-07-05T08:00:00Z", "Brazil",        "Norway",      "บราซิล",          "นอร์เวย์",      "16"),
    ("2026-07-06", "2026-07-06T00:00:00Z", "2026-07-05T08:00:00Z", "Mexico",        "England",     "เม็กซิโก",        "อังกฤษ",        "16"),
    ("2026-07-07", "2026-07-06T19:00:00Z", "2026-07-06T08:00:00Z", "Portugal",      "Spain",       "โปรตุเกส",        "สเปน",          "16"),
    ("2026-07-07", "2026-07-07T00:00:00Z", "2026-07-06T08:00:00Z", "USA",           "Belgium",     "สหรัฐ",           "เบลเยียม",      "16"),
]


def main():
    config = json.load(open("config.json"))
    conn = get_db(config)
    init_schema(conn)

    for row in MATCHES:
        conn.execute("""
            INSERT OR IGNORE INTO matches
            (match_date_ict, kickoff_utc, deadline_ict, home_team_en, away_team_en,
             home_team_th, away_team_th, round)
            VALUES (?,?,?,?,?,?,?,?)
        """, row)

    conn.commit()
    print(f"Schema created. {len(MATCHES)} matches seeded.")


if __name__ == "__main__":
    main()
