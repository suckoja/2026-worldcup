# World Cup 2026 LINE Bot — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Flask-based LINE group bot that parses member predictions, fetches World Cup results, calculates standings, and serves a local HTML dashboard.

**Architecture:** Single Flask process handles LINE webhooks and HTML dashboard. SQLite stores all state. Predictions parsed from free-text messages via regex. Results fetched from football-data.org on `/sync` command only.

**Tech Stack:** Python 3.11+, Flask, line-bot-sdk v3 (`linebot[v3]`), requests, SQLite (stdlib), pytest

## Global Constraints

- Timezone: all deadlines and display in ICT (UTC+7)
- Prediction separators: `:`, `-` (hyphen), `–` (en-dash U+2013)
- Strict score format only: `<team> \s* \d+ \s* [sep] \s* \d+ \s* <team>`
- Last prediction wins on duplicate (same player, same match)
- Admin LINE user ID from `config.json` — non-admin `/seed` and `/sync` silently ignored
- All configs hot-reload per request (no restart needed)
- Port: 8000

---

## File Map

```
bot.py                          # Flask app: webhook routing, dashboard routes
parser.py                       # Prediction regex extractor
db.py                           # SQLite connection + all queries
scoring.py                      # Points calculation
fetcher.py                      # football-data.org API client
commands.py                     # /stand /result /seed /sync /help handlers
config.json                     # Secrets (gitignored)
players.json                    # Player aliases (hot-reload)
teams.json                      # Thai/English team name map (hot-reload)
scoring_rules.json              # Points per round (hot-reload)
seeds/
  init_db.py                    # Creates schema + seeds match schedule
  seed_predictions.py           # CLI tool to bulk-seed past predictions
dashboard/
  templates/dashboard.html      # Jinja2 template
test_parser.py                  # Parser unit tests
test_scoring.py                 # Scoring unit tests
requirements.txt
```

---

## Task 1: Project Setup + Dependencies

**Files:**
- Create: `requirements.txt`
- Create: `config.json`
- Create: `players.json`
- Create: `teams.json`
- Create: `scoring_rules.json`

**Interfaces:**
- Produces: `load_config() -> dict` used by all modules

- [ ] **Step 1: Create requirements.txt**

```
flask==3.0.3
line-bot-sdk[v3]==3.11.0
requests==2.32.3
pytest==8.2.2
pytz==2024.1
```

- [ ] **Step 2: Install dependencies**

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Expected: no errors, packages installed.

- [ ] **Step 3: Create config.json**

```json
{
  "LINE_CHANNEL_SECRET": "YOUR_CHANNEL_SECRET",
  "LINE_CHANNEL_ACCESS_TOKEN": "YOUR_CHANNEL_ACCESS_TOKEN",
  "FOOTBALL_DATA_API_KEY": "YOUR_API_KEY",
  "ADMIN_LINE_USER_ID": "YOUR_LINE_USER_ID",
  "DB_PATH": "worldcup.db"
}
```

- [ ] **Step 4: Create players.json**

```json
[
  {"line_display_name": "Thomas Clover",       "aliases": ["thomas", "tom", "โทมัส"]},
  {"line_display_name": "Kritsana Th.",         "aliases": ["kritsana", "กฤษณะ", "นา"]},
  {"line_display_name": "Nuttapon Momo",        "aliases": ["momo", "นัท", "nuttapon"]},
  {"line_display_name": "Trisit Bobby_osk119",  "aliases": ["trisit", "bobby"]},
  {"line_display_name": "Khomkrit(Benz) SITEM", "aliases": ["benz", "khomkrit"]},
  {"line_display_name": "Wattana",              "aliases": ["วัฒนะ", "wattana"]},
  {"line_display_name": "AoB42🗝",              "aliases": ["aob", "ao"]},
  {"line_display_name": "JIRAWUT",              "aliases": ["jirawut", "จิรวุฒิ"]},
  {"line_display_name": "PJ",                   "aliases": ["pj"]},
  {"line_display_name": "Chaiwat I._Gap ^_^",   "aliases": ["chaiwat", "gap", "ชัยวัฒน์"]},
  {"line_display_name": "saravuts_เอ",           "aliases": ["เอ", "saravut", "สราวุฒิ"]},
  {"line_display_name": "Trinity",              "aliases": ["trinity"]},
  {"line_display_name": "supagorn",             "aliases": ["supagorn", "ศุภกร"]},
  {"line_display_name": "kwang",                "aliases": ["kwang", "กวาง"]},
  {"line_display_name": "SIRICHAI.159",         "aliases": ["sirichai", "ศิริชัย"]},
  {"line_display_name": "Piyaporn",             "aliases": ["piyaporn", "ปิยะพร"]},
  {"line_display_name": "Art",                  "aliases": ["art", "อาร์ท"]},
  {"line_display_name": "Ryu42♾",               "aliases": ["ryu", "ริว"]}
]
```

- [ ] **Step 5: Create teams.json**

```json
{
  "บราซิล": "Brazil",
  "ญี่ปุ่น": "Japan",
  "เยอรมัน": "Germany",
  "เยอรมนี": "Germany",
  "ปารากวัย": "Paraguay",
  "เนเธอแลนด์": "Netherlands",
  "เนเธอร์แลนด์": "Netherlands",
  "โมรอคโค": "Morocco",
  "โมร็อกโก": "Morocco",
  "แอฟริกาใต้": "South Africa",
  "อาฟริกา": "South Africa",
  "แคนาดา": "Canada",
  "นอร์เวย์": "Norway",
  "ไอวอรีโคสต์": "Ivory Coast",
  "โกตดิวัวร์": "Ivory Coast",
  "ฝรั่งเศส": "France",
  "สวีเดน": "Sweden",
  "เม็กซิโก": "Mexico",
  "เอกวาดอร์": "Ecuador",
  "อังกฤษ": "England",
  "คองโก": "Congo DR",
  "สหรัฐ": "USA",
  "อเมริกา": "USA",
  "บอสเนีย": "Bosnia",
  "เบลเยียม": "Belgium",
  "สเปน": "Spain",
  "ออสเตรีย": "Austria",
  "โปรตุเกส": "Portugal",
  "โครเอเชีย": "Croatia",
  "สวิตเซอร์แลนด์": "Switzerland",
  "แอลจีเรีย": "Algeria",
  "ออสเตรเลีย": "Australia",
  "อียิปต์": "Egypt",
  "อาร์เจนตินา": "Argentina",
  "เคปเวิร์ด": "Cape Verde",
  "โคลอมเบีย": "Colombia",
  "กานา": "Ghana",
  "Brazil": "Brazil",
  "Japan": "Japan",
  "Germany": "Germany",
  "Paraguay": "Paraguay",
  "Netherlands": "Netherlands",
  "Morocco": "Morocco",
  "South Africa": "South Africa",
  "Canada": "Canada",
  "Norway": "Norway",
  "Ivory Coast": "Ivory Coast",
  "France": "France",
  "Sweden": "Sweden",
  "Mexico": "Mexico",
  "Ecuador": "Ecuador",
  "England": "England",
  "Congo DR": "Congo DR",
  "USA": "USA",
  "Bosnia": "Bosnia",
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
  "Cape Verde": "Cape Verde",
  "Colombia": "Colombia",
  "Ghana": "Ghana"
}
```

- [ ] **Step 6: Create scoring_rules.json**

```json
{
  "32":    {"exact": 2, "correct": 1, "wrong": 0},
  "16":    {"exact": 4, "correct": 2, "wrong": 0},
  "8":     {"exact": 6, "correct": 3, "wrong": 0},
  "4":     {"exact": 8, "correct": 4, "wrong": 0},
  "final": {"exact": 8, "correct": 4, "wrong": 0}
}
```

- [ ] **Step 7: Create .gitignore**

```
config.json
venv/
__pycache__/
*.pyc
worldcup.db
```

- [ ] **Step 8: Commit**

```bash
git init
git add requirements.txt players.json teams.json scoring_rules.json .gitignore
git commit -m "feat: project setup and config files"
```

---

## Task 2: Database Schema + Seed Script

**Files:**
- Create: `db.py`
- Create: `seeds/init_db.py`

**Interfaces:**
- Produces:
  - `get_db(config: dict) -> sqlite3.Connection`
  - `init_schema(conn)`
  - All queries used by later tasks (defined in Task 4)

- [ ] **Step 1: Write test for schema creation**

```python
# test_db.py
import sqlite3, tempfile, os
from db import get_db, init_schema

def test_schema_creates_tables():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        conn = get_db({"DB_PATH": path})
        init_schema(conn)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "players" in tables
        assert "matches" in tables
        assert "predictions" in tables
    finally:
        os.unlink(path)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest test_db.py -v
```
Expected: FAIL — `db` module not found.

- [ ] **Step 3: Create db.py with schema**

```python
import sqlite3
import json

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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest test_db.py -v
```
Expected: PASS.

- [ ] **Step 5: Create seeds/init_db.py**

```python
#!/usr/bin/env python3
"""Run once to create DB schema and seed match schedule."""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import get_db, init_schema

MATCHES = [
    # (match_date_ict, kickoff_utc, deadline_ict, home_en, away_en, home_th, away_th, round)
    ("2026-06-28", "2026-06-28T16:00:00Z", "2026-06-28T08:00:00Z", "South Africa", "Canada",      "แอฟริกาใต้",       "แคนาดา",       "32"),
    ("2026-06-30", "2026-06-29T17:00:00Z", "2026-06-29T08:00:00Z", "Brazil",        "Japan",       "บราซิล",          "ญี่ปุ่น",        "32"),
    ("2026-06-30", "2026-06-29T20:30:00Z", "2026-06-29T08:00:00Z", "Germany",       "Paraguay",    "เยอรมัน",         "ปารากวัย",      "32"),
    ("2026-06-30", "2026-06-30T01:00:00Z", "2026-06-29T08:00:00Z", "Netherlands",   "Morocco",     "เนเธอร์แลนด์",    "โมร็อกโก",      "32"),
    ("2026-07-01", "2026-06-30T17:00:00Z", "2026-06-30T08:00:00Z", "Ivory Coast",   "Norway",      "ไอวอรีโคสต์",     "นอร์เวย์",      "32"),
    ("2026-07-01", "2026-06-30T21:00:00Z", "2026-06-30T08:00:00Z", "France",        "Sweden",      "ฝรั่งเศส",        "สวีเดน",        "32"),
    ("2026-07-01", "2026-07-01T01:00:00Z", "2026-06-30T08:00:00Z", "Mexico",        "Ecuador",     "เม็กซิโก",        "เอกวาดอร์",     "32"),
    ("2026-07-02", "2026-07-02T16:00:00Z", "2026-07-01T08:00:00Z", "England",       "Congo DR",    "อังกฤษ",          "คองโก",        "32"),
    ("2026-07-03", "2026-07-02T19:00:00Z", "2026-07-02T08:00:00Z", "USA",           "Bosnia",      "สหรัฐ",           "บอสเนีย",       "32"),
    ("2026-07-03", "2026-07-02T21:00:00Z", "2026-07-02T08:00:00Z", "Belgium",       "TBD",         "เบลเยียม",        "TBD",          "32"),
    ("2026-07-03", "2026-07-02T23:00:00Z", "2026-07-02T08:00:00Z", "Spain",         "Austria",     "สเปน",            "ออสเตรีย",      "32"),
    ("2026-07-04", "2026-07-03T18:00:00Z", "2026-07-03T08:00:00Z", "Australia",     "Egypt",       "ออสเตรเลีย",      "อียิปต์",       "32"),
    ("2026-07-04", "2026-07-03T19:00:00Z", "2026-07-03T08:00:00Z", "Portugal",      "Croatia",     "โปรตุเกส",        "โครเอเชีย",     "32"),
    ("2026-07-04", "2026-07-03T23:00:00Z", "2026-07-03T08:00:00Z", "Switzerland",   "Algeria",     "สวิตเซอร์แลนด์",  "แอลจีเรีย",    "32"),
    ("2026-07-05", "2026-07-04T22:00:00Z", "2026-07-04T08:00:00Z", "Argentina",     "Cape Verde",  "อาร์เจนตินา",     "เคปเวิร์ด",     "32"),
    ("2026-07-05", "2026-07-05T01:30:00Z", "2026-07-04T08:00:00Z", "Colombia",      "Ghana",       "โคลอมเบีย",       "กานา",         "32"),
]

def main():
    config = json.load(open("config.json"))
    conn = get_db(config)
    init_schema(conn)

    for (match_date_ict, kickoff_utc, deadline_ict, home_en, away_en, home_th, away_th, rnd) in MATCHES:
        conn.execute("""
            INSERT OR IGNORE INTO matches
            (match_date_ict, kickoff_utc, deadline_ict, home_team_en, away_team_en, home_team_th, away_team_th, round)
            VALUES (?,?,?,?,?,?,?,?)
        """, (match_date_ict, kickoff_utc, deadline_ict, home_en, away_en, home_th, away_th, rnd))

    conn.commit()
    print(f"Schema created. {len(MATCHES)} matches seeded.")

if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run seed script**

```bash
python seeds/init_db.py
```
Expected: `Schema created. 16 matches seeded.`

- [ ] **Step 7: Verify**

```bash
sqlite3 worldcup.db "SELECT match_date_ict, home_team_en, away_team_en FROM matches ORDER BY kickoff_utc;"
```
Expected: 16 rows, South Africa vs Canada first.

- [ ] **Step 8: Commit**

```bash
git add db.py seeds/init_db.py test_db.py
git commit -m "feat: database schema and match schedule seed"
```

---

## Task 3: Parser

**Files:**
- Create: `parser.py`
- Create: `test_parser.py`

**Interfaces:**
- Produces: `parse_predictions(text: str, teams: dict) -> list[tuple[str, int, int, str]]`
  - Returns list of `(home_team_en, home_score, away_score, away_team_en)`
  - Empty list if no valid predictions found

- [ ] **Step 1: Write failing tests**

```python
# test_parser.py
import json
from parser import parse_predictions

TEAMS = json.load(open("teams.json"))

def test_colon_separator():
    result = parse_predictions("บราซิล 2:1 ญี่ปุ่น", TEAMS)
    assert result == [("Brazil", 2, 1, "Japan")]

def test_hyphen_separator():
    result = parse_predictions("บราซิล 2-1 ญี่ปุ่น", TEAMS)
    assert result == [("Brazil", 2, 1, "Japan")]

def test_endash_separator():
    result = parse_predictions("บราซิล 2–1 ญี่ปุ่น", TEAMS)
    assert result == [("Brazil", 2, 1, "Japan")]

def test_no_space_between_score_and_team():
    result = parse_predictions("เยอรมนี 2–0ปารากวัย", TEAMS)
    assert result == [("Germany", 2, 0, "Paraguay")]

def test_spaces_around_separator():
    result = parse_predictions("เนเธอร์แลนด์ 1 – 0โมร็อกโก", TEAMS)
    assert result == [("Netherlands", 1, 0, "Morocco")]

def test_english_team_names():
    result = parse_predictions("Brazil 2:1 Japan", TEAMS)
    assert result == [("Brazil", 2, 1, "Japan")]

def test_multi_line_three_matches():
    text = "บราซิล 2:1 ญี่ปุ่น\nเยอรมัน 2:0 ปารากวัย\nเนเธอร์แลนด์ 1:1 โมรอคโค"
    result = parse_predictions(text, TEAMS)
    assert len(result) == 3
    assert result[0] == ("Brazil", 2, 1, "Japan")
    assert result[1] == ("Germany", 2, 0, "Paraguay")
    assert result[2] == ("Netherlands", 1, 1, "Morocco")

def test_multi_line_last_wins():
    text = "บราซิล 2:1 ญี่ปุ่น\nบราซิล 1:0 ญี่ปุ่น"
    result = parse_predictions(text, TEAMS)
    assert result == [("Brazil", 1, 0, "Japan")]

def test_invalid_format_no_separator():
    result = parse_predictions("บราซิล 2 ญี่ปุ่น", TEAMS)
    assert result == []

def test_slash_separator_rejected():
    result = parse_predictions("บราซิล 2/1 ญี่ปุ่น", TEAMS)
    assert result == []

def test_non_prediction_text_ignored():
    result = parse_predictions("ขอตารางคะแนนด้วยนะ", TEAMS)
    assert result == []

def test_command_ignored():
    result = parse_predictions("/stand", TEAMS)
    assert result == []

def test_unknown_team_ignored():
    result = parse_predictions("ดาวอังคาร 2:1 ดาวพฤหัส", TEAMS)
    assert result == []

def test_draw():
    result = parse_predictions("บราซิล 0:0 ญี่ปุ่น", TEAMS)
    assert result == [("Brazil", 0, 0, "Japan")]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest test_parser.py -v
```
Expected: all FAIL — `parser` module not found.

- [ ] **Step 3: Implement parser.py**

```python
import re
from typing import Optional

# Matches: <anything> <digits> <sep> <digits> <anything>
# Sep: colon, hyphen, en-dash (U+2013)
_SCORE_RE = re.compile(r'(.+?)\s*(\d+)\s*[:-–]\s*(\d+)\s*(.+)', re.UNICODE)

def _match_team(text: str, teams: dict) -> Optional[str]:
    """Return canonical English team name or None."""
    text = text.strip()
    # Try exact match first (handles multi-word English names)
    if text in teams:
        return teams[text]
    # Try case-insensitive English match
    text_lower = text.lower()
    for k, v in teams.items():
        if k.lower() == text_lower:
            return v
    return None

def parse_predictions(text: str, teams: dict) -> list[tuple[str, int, int, str]]:
    """
    Parse all score predictions from a multi-line message.
    Returns list of (home_en, home_score, away_score, away_en).
    Last prediction for a given home+away pair wins.
    """
    if text.startswith("/"):
        return []

    seen: dict[tuple[str, str], tuple[str, int, int, str]] = {}

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _SCORE_RE.match(line)
        if not m:
            continue
        before, h, a, after = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
        home = _match_team(before, teams)
        away = _match_team(after, teams)
        if home and away:
            seen[(home, away)] = (home, h, a, away)

    return list(seen.values())
```

- [ ] **Step 4: Run tests**

```bash
pytest test_parser.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add parser.py test_parser.py
git commit -m "feat: prediction message parser with strict score format"
```

---

## Task 4: Scoring Engine

**Files:**
- Create: `scoring.py`
- Create: `test_scoring.py`

**Interfaces:**
- Produces:
  - `score_prediction(predicted: tuple[int,int], actual: tuple[int,int], round: str, rules: dict) -> int`
  - `recalculate_all(conn, rules: dict)`

- [ ] **Step 1: Write failing tests**

```python
# test_scoring.py
from scoring import score_prediction

RULES = {
    "32":    {"exact": 2, "correct": 1, "wrong": 0},
    "16":    {"exact": 4, "correct": 2, "wrong": 0},
    "8":     {"exact": 6, "correct": 3, "wrong": 0},
    "4":     {"exact": 8, "correct": 4, "wrong": 0},
    "final": {"exact": 8, "correct": 4, "wrong": 0},
}

def test_exact_score_round32():
    assert score_prediction((1, 0), (1, 0), "32", RULES) == 2

def test_correct_result_round32():
    assert score_prediction((2, 0), (1, 0), "32", RULES) == 1

def test_wrong_result_round32():
    assert score_prediction((0, 1), (1, 0), "32", RULES) == 0

def test_exact_draw():
    assert score_prediction((1, 1), (1, 1), "32", RULES) == 2

def test_correct_draw_different_score():
    assert score_prediction((0, 0), (2, 2), "32", RULES) == 1

def test_wrong_predicted_draw_actual_win():
    assert score_prediction((1, 1), (2, 1), "32", RULES) == 0

def test_exact_score_round16():
    assert score_prediction((2, 1), (2, 1), "16", RULES) == 4

def test_correct_result_round16():
    assert score_prediction((3, 1), (2, 1), "16", RULES) == 2

def test_exact_score_round8():
    assert score_prediction((1, 0), (1, 0), "8", RULES) == 6

def test_exact_score_round4():
    assert score_prediction((1, 0), (1, 0), "4", RULES) == 8
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest test_scoring.py -v
```
Expected: all FAIL.

- [ ] **Step 3: Implement scoring.py**

```python
import sqlite3

def _result(h: int, a: int) -> int:
    """Return 1 (home win), 0 (draw), -1 (away win)."""
    return (h > a) - (h < a)

def score_prediction(
    predicted: tuple[int, int],
    actual: tuple[int, int],
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
```

- [ ] **Step 4: Run tests**

```bash
pytest test_scoring.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add scoring.py test_scoring.py
git commit -m "feat: scoring engine with per-round point rules"
```

---

## Task 5: DB Query Helpers

**Files:**
- Modify: `db.py` — add all query functions

**Interfaces:**
- Produces:
  - `load_players(path="players.json") -> list[dict]`
  - `resolve_player(name: str, players: list[dict]) -> tuple[str|None, list[str]]`
    - Returns `(line_display_name, [])` on unique match, `(None, [candidates])` on ambiguous, `(None, [])` on no match
  - `upsert_player(conn, line_display_name: str)`
  - `get_match_by_teams(conn, home_en: str, away_en: str) -> sqlite3.Row|None`
  - `get_match_by_id(conn, match_id: int) -> sqlite3.Row|None`
  - `upsert_prediction(conn, player_id, match_id, home_pred, away_pred, line_message_id, submitted_at)`
  - `delete_prediction_by_message_id(conn, message_id: str) -> bool`
  - `get_standings(conn) -> list[sqlite3.Row]`
  - `get_player_history(conn, player_id: int) -> list[sqlite3.Row]`
  - `get_today_predictions(conn, date_ict: str) -> list[sqlite3.Row]`

- [ ] **Step 1: Add helper functions to db.py**

Append to `db.py`:

```python
import json
from datetime import datetime, timezone, timedelta

ICT = timezone(timedelta(hours=7))

def now_ict() -> str:
    return datetime.now(ICT).strftime("%Y-%m-%dT%H:%M:%S")

def today_ict() -> str:
    return datetime.now(ICT).strftime("%Y-%m-%d")

def load_players(path: str = "players.json") -> list[dict]:
    return json.load(open(path, encoding="utf-8"))

def resolve_player(name: str, players: list[dict]) -> tuple:
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

def upsert_player(conn: sqlite3.Connection, line_display_name: str, aliases: list = None):
    conn.execute(
        "INSERT OR IGNORE INTO players (line_display_name, aliases) VALUES (?, ?)",
        (line_display_name, json.dumps(aliases or []))
    )
    conn.commit()

def get_player_id(conn: sqlite3.Connection, line_display_name: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM players WHERE line_display_name = ?", (line_display_name,)
    ).fetchone()
    return row["id"] if row else None

def get_match_by_teams(conn: sqlite3.Connection, home_en: str, away_en: str) -> sqlite3.Row | None:
    return conn.execute("""
        SELECT * FROM matches
        WHERE (home_team_en = ? AND away_team_en = ?)
           OR (home_team_en = ? AND away_team_en = ?)
    """, (home_en, away_en, away_en, home_en)).fetchone()

def get_match_by_id(conn: sqlite3.Connection, match_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()

def upsert_prediction(conn: sqlite3.Connection, player_id: int, match_id: int,
                      home_pred: int, away_pred: int, line_message_id: str, submitted_at: str):
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
        return False  # locked
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
```

- [ ] **Step 2: Verify db.py imports cleanly**

```bash
python -c "import db; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add db.py
git commit -m "feat: database query helpers"
```

---

## Task 6: Result Fetcher

**Files:**
- Create: `fetcher.py`

**Interfaces:**
- Produces: `sync_results(conn, api_key: str) -> list[str]`
  - Returns list of human-readable result strings e.g. `["Brazil 2-1 Japan", ...]`

- [ ] **Step 1: Create fetcher.py**

```python
import requests
import sqlite3
from datetime import datetime, timezone

# football-data.org API team name → our canonical English name
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

def sync_results(conn: sqlite3.Connection, api_key: str) -> list[str]:
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
    for match in data.get("matches", []):
        home_api = match["homeTeam"]["name"]
        away_api = match["awayTeam"]["name"]
        home_en = API_TEAM_MAP.get(home_api)
        away_en = API_TEAM_MAP.get(away_api)
        if not home_en or not away_en:
            continue

        score = match.get("score", {})
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
    return updated
```

- [ ] **Step 2: Verify imports**

```bash
python -c "import fetcher; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add fetcher.py
git commit -m "feat: football-data.org result fetcher"
```

---

## Task 7: Command Handlers

**Files:**
- Create: `commands.py`

**Interfaces:**
- Consumes: `db.*`, `scoring.recalculate_all`, `fetcher.sync_results`
- Produces: `handle_command(text: str, conn, config: dict, players: list, rules: dict, teams: dict) -> str | None`
  - Returns reply string or None (ignore)

- [ ] **Step 1: Create commands.py**

```python
import json
import sqlite3
from datetime import datetime, timezone, timedelta

import db
import scoring
import fetcher

ICT = timezone(timedelta(hours=7))

def _is_admin(user_id: str, config: dict) -> bool:
    return user_id == config.get("ADMIN_LINE_USER_ID", "")

def _standings_text(conn) -> str:
    rows = db.get_standings(conn)
    today = datetime.now(ICT).strftime("%d/%m/%Y")
    lines = [f"🏆 ตารางคะแนน World Cup 2026", f"(อัพเดท: {today})", ""]
    rank = 1
    prev_pts = None
    for i, row in enumerate(rows):
        pts = row["total_points"]
        if pts != prev_pts:
            rank = i + 1
            prev_pts = pts
        star = " ⭐" if pts > 0 and rank == 1 else ""
        lines.append(f"{rank:2}. {row['line_display_name']:<22} {pts} แต้ม{star}")
    return "\n".join(lines)

def _result_player_text(conn, player_id: int, display_name: str) -> str:
    rows = db.get_player_history(conn, player_id)
    if not rows:
        return f"ไม่พบประวัติการทายของ {display_name}"

    lines = [f"📊 {display_name} — ประวัติการทาย", ""]
    current_date = None
    total_pts = 0
    match_count = 0

    for row in rows:
        if row["match_date_ict"] != current_date:
            current_date = row["match_date_ict"]
            d = datetime.strptime(current_date, "%Y-%m-%d").strftime("%d/%m/%Y")
            lines.append(f"📅 {d}")

        home_th = row["home_team_th"] or row["home_team_en"]
        away_th = row["away_team_th"] or row["away_team_en"]
        pred = f"{row['home_pred']}-{row['away_pred']}"
        actual = f"{row['home_score']}-{row['away_score']}" if row["home_score"] is not None else "⏳"
        pts = row["points"]
        pts_str = f"✅ {pts} แต้ม" if pts is not None else "—"
        lines.append(f"{home_th} vs {away_th}")
        lines.append(f"  ทาย: {pred}  |  จริง: {actual}  |  {pts_str}")

        if pts is not None:
            total_pts += pts
            match_count += 1

    lines.append("")
    lines.append(f"รวม: {total_pts} แต้ม ({match_count} นัด)")
    return "\n".join(lines)

def _result_today_text(conn) -> str:
    today = db.today_ict()
    rows = db.get_today_predictions(conn, today)
    if not rows:
        return "ไม่มีการแข่งขันวันนี้"

    d_display = datetime.strptime(today, "%Y-%m-%d").strftime("%d/%m/%Y")
    lines = [f"📅 ผลการทาย {d_display}", ""]
    current_match = None

    for row in rows:
        match_key = (row["home_team_en"], row["away_team_en"])
        if match_key != current_match:
            current_match = match_key
            home_th = row["home_team_th"] or row["home_team_en"]
            away_th = row["away_team_th"] or row["away_team_en"]
            actual = f"{row['home_score']}-{row['away_score']}" if row["home_score"] is not None else "⏳ รอผล"
            lines.append(f"⚽ {home_th} vs {away_th}")
            lines.append(f"  จริง: {actual}")

        if row["line_display_name"]:
            pred = f"{row['home_pred']}-{row['away_pred']}"
            pts = f" ({row['points']} แต้ม)" if row["points"] is not None else ""
            lines.append(f"  {row['line_display_name']:<22} {pred}{pts}")

    return "\n".join(lines)

def _help_text() -> str:
    return (
        "คำสั่งที่ใช้ได้:\n"
        "/stand หรือ /table — ตารางคะแนน\n"
        "/result [ชื่อ] — ประวัติการทายของผู้เล่น\n"
        "/result today — การทายวันนี้ทุกคน\n"
        "/sync — ดึงผลการแข่งขันล่าสุด (admin)\n"
        "/seed [ชื่อ] [วันที่] [ทีมเหย้า] [สกอร์] [ทีมเยือน] — บันทึกย้อนหลัง (admin)\n"
        "/help — แสดงคำสั่ง"
    )

def handle_command(
    text: str,
    user_id: str,
    conn: sqlite3.Connection,
    config: dict,
    players: list,
    rules: dict,
    teams: dict
) -> str | None:
    parts = text.strip().split()
    if not parts:
        return None
    cmd = parts[0].lower()

    if cmd in ("/stand", "/table"):
        return _standings_text(conn)

    if cmd == "/result":
        if len(parts) < 2:
            return _result_today_text(conn)
        arg = " ".join(parts[1:])
        if arg.lower() == "today":
            return _result_today_text(conn)
        name, candidates = db.resolve_player(arg, players)
        if name:
            player_id = db.get_player_id(conn, name)
            if not player_id:
                db.upsert_player(conn, name)
                player_id = db.get_player_id(conn, name)
            return _result_player_text(conn, player_id, name)
        if candidates:
            return "❌ ชื่อตรงกับหลายคน:\n" + "\n".join(f"- {c}" for c in candidates) + "\nพิมพ์ชื่อให้ชัดขึ้น"
        all_names = "\n".join(f"- {p['line_display_name']}" for p in players)
        return f"❌ ไม่พบผู้เล่น '{arg}'\nผู้เล่นทั้งหมด:\n{all_names}"

    if cmd == "/help":
        return _help_text()

    if cmd == "/sync":
        if not _is_admin(user_id, config):
            return None
        try:
            updated = fetcher.sync_results(conn, config["FOOTBALL_DATA_API_KEY"])
            scoring.recalculate_all(conn, rules)
            if not updated:
                return "ไม่มีผลใหม่"
            result_lines = "\n".join(f"✅ {r}" for r in updated)
            return (
                f"🔄 กำลังดึงผลการแข่งขัน...\n\n"
                f"{result_lines}\n\n"
                f"📊 คำนวณคะแนนเสร็จแล้ว — อัพเดท {len(updated)} นัด\n"
                f"พิมพ์ /stand เพื่อดูตาราง"
            )
        except Exception as e:
            return f"❌ ดึงข้อมูลไม่ได้ ลองใหม่ภายหลัง ({e})"

    if cmd == "/seed":
        if not _is_admin(user_id, config):
            return None
        # /seed [player] [date YYYY-MM-DD] [home] [H-A] [away]
        # e.g. /seed thomas 2026-06-28 "South Africa" 0-2 Canada
        if len(parts) < 6:
            return "❌ รูปแบบ: /seed [ชื่อ] [YYYY-MM-DD] [ทีมเหย้า] [H-A] [ทีมเยือน]"
        player_arg = parts[1]
        date_arg = parts[2]
        score_arg = parts[-2]
        home_arg = " ".join(parts[3:-2]).strip('"')
        away_arg = parts[-1].strip('"')

        name, candidates = db.resolve_player(player_arg, players)
        if not name:
            if candidates:
                return "❌ ชื่อตรงกับหลายคน: " + ", ".join(candidates)
            return f"❌ ไม่พบผู้เล่น '{player_arg}'"

        import re
        score_m = re.match(r'(\d+)[:\-–](\d+)', score_arg)
        if not score_m:
            return f"❌ สกอร์ไม่ถูกต้อง '{score_arg}' ใช้รูปแบบ H-A เช่น 0-2"

        home_pred, away_pred = int(score_m.group(1)), int(score_m.group(2))

        # Resolve team names
        home_en = teams.get(home_arg) or (home_arg if home_arg in teams.values() else None)
        away_en = teams.get(away_arg) or (away_arg if away_arg in teams.values() else None)
        if not home_en:
            return f"❌ ไม่พบทีม '{home_arg}'"
        if not away_en:
            return f"❌ ไม่พบทีม '{away_arg}'"

        match_row = db.get_match_by_teams(conn, home_en, away_en)
        if not match_row:
            return f"❌ ไม่พบนัด {home_en} vs {away_en}"

        db.upsert_player(conn, name)
        player_id = db.get_player_id(conn, name)
        db.upsert_prediction(conn, player_id, match_row["id"], home_pred, away_pred,
                             None, f"{date_arg}T00:00:00")
        home_th = match_row["home_team_th"] or home_en
        away_th = match_row["away_team_th"] or away_en
        d = datetime.strptime(match_row["match_date_ict"], "%Y-%m-%d").strftime("%d/%m/%Y")
        return (
            f"✅ บันทึกการทายแล้ว\n"
            f"ผู้เล่น: {name}\n"
            f"นัด: {home_th} vs {away_th} ({d})\n"
            f"ทาย: {home_pred}-{away_pred}\n"
            f"(เขียนทับข้อมูลเดิม ถ้ามี)"
        )

    return None
```

- [ ] **Step 2: Verify imports**

```bash
python -c "import commands; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add commands.py
git commit -m "feat: command handlers for /stand /result /seed /sync /help"
```

---

## Task 8: Flask Webhook + Bot Entry Point

**Files:**
- Create: `bot.py`

**Interfaces:**
- Consumes: `parser.parse_predictions`, `commands.handle_command`, `db.*`, `scoring.*`
- Produces: running Flask server on port 8000

- [ ] **Step 1: Create bot.py**

```python
import json
import sqlite3
from datetime import datetime, timezone, timedelta

from flask import Flask, request, abort, render_template
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    ReplyMessageRequest, TextMessage
)
from linebot.v3.webhooks import (
    MessageEvent, TextMessageContent, UnsendEvent
)

import db
import commands
import parser as pred_parser

app = Flask(__name__, template_folder="dashboard")

# --- Config helpers (hot-reload) ---

def load_config() -> dict:
    return json.load(open("config.json", encoding="utf-8"))

def load_players() -> list:
    return json.load(open("players.json", encoding="utf-8"))

def load_teams() -> dict:
    return json.load(open("teams.json", encoding="utf-8"))

def load_rules() -> dict:
    return json.load(open("scoring_rules.json", encoding="utf-8"))

def get_conn(config: dict) -> sqlite3.Connection:
    return db.get_db(config)

ICT = timezone(timedelta(hours=7))

# --- LINE SDK setup (lazy, per request) ---

def _get_line_api(config: dict):
    cfg = Configuration(access_token=config["LINE_CHANNEL_ACCESS_TOKEN"])
    return ApiClient(cfg), MessagingApi(ApiClient(cfg))

def reply(reply_token: str, text: str, config: dict):
    _, api = _get_line_api(config)
    api.reply_message(ReplyMessageRequest(
        reply_token=reply_token,
        messages=[TextMessage(text=text)]
    ))

# --- Webhook ---

@app.route("/webhook", methods=["POST"])
def webhook():
    config = load_config()
    handler = WebhookHandler(config["LINE_CHANNEL_SECRET"])
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    events = json.loads(body).get("events", [])
    players = load_players()
    teams = load_teams()
    rules = load_rules()
    conn = get_conn(config)

    # Ensure all known players exist in DB
    for p in players:
        db.upsert_player(conn, p["line_display_name"], p.get("aliases", []))

    for event in events:
        event_type = event.get("type")
        reply_token = event.get("replyToken")
        source = event.get("source", {})
        user_id = source.get("userId", "")

        if event_type == "message":
            msg = event.get("message", {})
            if msg.get("type") != "text":
                continue
            text = msg.get("text", "").strip()
            message_id = msg.get("id")

            if text.startswith("/"):
                response = commands.handle_command(
                    text, user_id, conn, config, players, rules, teams
                )
                if response and reply_token:
                    reply(reply_token, response, config)
            else:
                # Try prediction parse
                predictions = pred_parser.parse_predictions(text, teams)
                submitted_at = datetime.now(ICT).strftime("%Y-%m-%dT%H:%M:%S")

                for (home_en, home_pred, away_pred, away_en) in predictions:
                    match_row = db.get_match_by_teams(conn, home_en, away_en)
                    if not match_row:
                        continue

                    # Deadline check
                    deadline = datetime.fromisoformat(match_row["deadline_ict"])
                    deadline = deadline.replace(tzinfo=ICT)
                    now = datetime.now(ICT)

                    if now > deadline:
                        if reply_token:
                            home_th = match_row["home_team_th"] or home_en
                            away_th = match_row["away_team_th"] or away_en
                            reply(reply_token,
                                  f"❌ หมดเวลาทาย {home_th} vs {away_th} แล้ว",
                                  config)
                        continue

                    # Resolve player from LINE display name
                    sender_name = event.get("source", {}).get("userId")
                    # Try to find player by LINE user ID — fall back to notify admin
                    # ponytail: we store by display name; LINE userId not easily mapped here
                    # Admin must /seed if bot can't auto-resolve
                    # For group messages, get displayName via profile API if needed
                    # Simple approach: match sender profile name when available
                    display_name = None
                    try:
                        client, api = _get_line_api(config)
                        profile = api.get_group_member_profile(
                            source.get("groupId"), user_id
                        )
                        display_name = profile.display_name
                    except Exception:
                        pass

                    if not display_name:
                        continue

                    resolved, _ = db.resolve_player(display_name, players)
                    if not resolved:
                        # Notify admin
                        admin_id = config.get("ADMIN_LINE_USER_ID")
                        if admin_id:
                            try:
                                _, api = _get_line_api(config)
                                from linebot.v3.messaging import PushMessageRequest
                                api.push_message(PushMessageRequest(
                                    to=admin_id,
                                    messages=[TextMessage(
                                        text=f"⚠️ ผู้เล่นใหม่: {display_name}\nกรุณาเพิ่มใน players.json"
                                    )]
                                ))
                            except Exception:
                                pass
                        continue

                    db.upsert_player(conn, resolved)
                    player_id = db.get_player_id(conn, resolved)
                    db.upsert_prediction(
                        conn, player_id, match_row["id"],
                        home_pred, away_pred, message_id, submitted_at
                    )

        elif event_type == "unsend":
            message_id = event.get("unsend", {}).get("messageId")
            if message_id:
                db.delete_prediction_by_message_id(conn, message_id)

    conn.close()
    return "OK", 200

# --- Dashboard ---

@app.route("/dashboard")
def dashboard():
    config = load_config()
    conn = get_conn(config)
    players = load_players()

    standings = db.get_standings(conn)

    # All matches
    matches = conn.execute(
        "SELECT * FROM matches ORDER BY kickoff_utc"
    ).fetchall()

    # Today's predictions
    today = db.today_ict()
    today_rows = db.get_today_predictions(conn, today)

    # Per-player history for detail view
    player_histories = {}
    for p in players:
        pid = db.get_player_id(conn, p["line_display_name"])
        if pid:
            player_histories[p["line_display_name"]] = db.get_player_history(conn, pid)

    conn.close()
    return render_template(
        "dashboard.html",
        standings=standings,
        matches=matches,
        today_rows=today_rows,
        player_histories=player_histories,
        today=today
    )

if __name__ == "__main__":
    app.run(port=8000, debug=True)
```

- [ ] **Step 2: Verify Flask starts**

```bash
python bot.py
```
Expected: `Running on http://127.0.0.1:8000`
Ctrl+C to stop.

- [ ] **Step 3: Commit**

```bash
git add bot.py
git commit -m "feat: Flask webhook handler and LINE message routing"
```

---

## Task 9: HTML Dashboard

**Files:**
- Create: `dashboard/templates/dashboard.html`

- [ ] **Step 1: Create dashboard directory**

```bash
mkdir -p dashboard/templates
```

- [ ] **Step 2: Create dashboard.html**

```html
<!DOCTYPE html>
<html lang="th">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>World Cup 2026 — Standings</title>
  <style>
    body { font-family: sans-serif; max-width: 900px; margin: 0 auto; padding: 1rem; background: #111; color: #eee; }
    h1, h2 { color: #f90; }
    table { width: 100%; border-collapse: collapse; margin-bottom: 2rem; }
    th, td { padding: 0.5rem 0.75rem; border: 1px solid #333; text-align: left; }
    th { background: #222; }
    tr:nth-child(even) { background: #1a1a1a; }
    .pts { font-weight: bold; color: #f90; }
    .exact { color: #4f4; }
    .correct { color: #4af; }
    .wrong { color: #f44; }
    .pending { color: #888; }
    details summary { cursor: pointer; padding: 0.5rem; background: #222; margin-bottom: 0.5rem; }
    details[open] summary { background: #333; }
  </style>
</head>
<body>
  <h1>🏆 World Cup 2026 Predictions</h1>

  <h2>Standings</h2>
  <table>
    <tr><th>#</th><th>Player</th><th>Points</th><th>Matches</th></tr>
    {% set ns = namespace(rank=1, prev_pts=-1, offset=0) %}
    {% for row in standings %}
      {% if row.total_points != ns.prev_pts %}
        {% set ns.rank = loop.index %}
        {% set ns.prev_pts = row.total_points %}
      {% endif %}
      <tr>
        <td>{{ ns.rank }}</td>
        <td>{{ row.line_display_name }}</td>
        <td class="pts">{{ row.total_points }}</td>
        <td>{{ row.matches_played }}</td>
      </tr>
    {% endfor %}
  </table>

  <h2>Match Schedule</h2>
  <table>
    <tr><th>Date (ICT)</th><th>Match</th><th>Result</th><th>Deadline</th></tr>
    {% for m in matches %}
    <tr>
      <td>{{ m.match_date_ict }}</td>
      <td>{{ m.home_team_th or m.home_team_en }} vs {{ m.away_team_th or m.away_team_en }}</td>
      <td>{% if m.home_score is not none %}{{ m.home_score }}-{{ m.away_score }}{% else %}⏳{% endif %}</td>
      <td>{{ m.deadline_ict[:10] }} 15:00</td>
    </tr>
    {% endfor %}
  </table>

  <h2>Today's Predictions ({{ today }})</h2>
  {% set current_match = namespace(key="") %}
  {% for row in today_rows %}
    {% set match_key = row.home_team_en + row.away_team_en %}
    {% if match_key != current_match.key %}
      {% set current_match.key = match_key %}
      <h3>⚽ {{ row.home_team_th or row.home_team_en }} vs {{ row.away_team_th or row.away_team_en }}
        {% if row.home_score is not none %} — {{ row.home_score }}-{{ row.away_score }}{% else %} — ⏳{% endif %}
      </h3>
      <table>
        <tr><th>Player</th><th>Prediction</th><th>Points</th></tr>
    {% endif %}
    {% if row.line_display_name %}
    <tr>
      <td>{{ row.line_display_name }}</td>
      <td>{{ row.home_pred }}-{{ row.away_pred }}</td>
      <td>{% if row.points is not none %}<span class="pts">{{ row.points }}</span>{% else %}<span class="pending">—</span>{% endif %}</td>
    </tr>
    {% endif %}
  {% endfor %}
  {% if not today_rows %}<p>No predictions yet.</p>{% endif %}

  <h2>Player History</h2>
  {% for name, history in player_histories.items() %}
  <details>
    <summary>{{ name }}</summary>
    {% if history %}
    <table>
      <tr><th>Date</th><th>Match</th><th>Prediction</th><th>Result</th><th>Points</th></tr>
      {% for row in history %}
      <tr>
        <td>{{ row.match_date_ict }}</td>
        <td>{{ row.home_team_th or row.home_team_en }} vs {{ row.away_team_th or row.away_team_en }}</td>
        <td>{{ row.home_pred }}-{{ row.away_pred }}</td>
        <td>{% if row.home_score is not none %}{{ row.home_score }}-{{ row.away_score }}{% else %}⏳{% endif %}</td>
        <td>{% if row.points is not none %}<span class="pts">{{ row.points }}</span>{% else %}<span class="pending">—</span>{% endif %}</td>
      </tr>
      {% endfor %}
    </table>
    {% else %}<p>No predictions yet.</p>{% endif %}
  </details>
  {% endfor %}
</body>
</html>
```

- [ ] **Step 3: Start bot and verify dashboard loads**

```bash
python bot.py
```
Open `http://localhost:8000/dashboard` — should show standings table (empty or seeded).

- [ ] **Step 4: Commit**

```bash
git add dashboard/templates/dashboard.html
git commit -m "feat: local HTML dashboard with standings, schedule, predictions"
```

---

## Task 10: Seed Past Data (Match 1)

**Files:**
- Create: `seeds/seed_predictions.py`

- [ ] **Step 1: Create seed_predictions.py**

```python
#!/usr/bin/env python3
"""Bulk seed past predictions. Edit PREDICTIONS list and run."""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import db, scoring

# Match 1: South Africa 0-1 Canada (2026-06-28)
PREDICTIONS = [
    # (player_alias, home_pred, away_pred, match_home_en, match_away_en, date)
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
]

def main():
    config = json.load(open("config.json"))
    players_data = json.load(open("players.json"))
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
        print(f"OK: {name} — {home_pred}-{away_pred}")
        ok += 1

    # Seed actual result for Match 1
    conn.execute(
        "UPDATE matches SET home_score=0, away_score=1 WHERE home_team_en='South Africa' AND away_team_en='Canada'"
    )
    conn.commit()
    print(f"\nResult seeded: South Africa 0-1 Canada")

    scoring.recalculate_all(conn, rules)
    print("Points recalculated.")
    print(f"\nSeeded {ok} predictions.")

    # Print standings
    rows = db.get_standings(conn)
    print("\n=== Standings ===")
    for i, row in enumerate(rows, 1):
        print(f"{i:2}. {row['line_display_name']:<25} {row['total_points']} pts")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run seed**

```bash
python seeds/seed_predictions.py
```
Expected output ends with:
```
=== Standings ===
 1. Nuttapon Momo          2 pts
 1. Khomkrit(Benz) SITEM   2 pts
 1. saravuts_เอ             2 pts
 4. Thomas Clover           1 pts
...
16. Trisit Bobby_osk119     0 pts
16. Trinity                 0 pts
```

- [ ] **Step 3: Verify against known standings**

Confirm top 3 have 2 pts, Trisit + Trinity have 0 pts. Matches manual calculation from session.

- [ ] **Step 4: Commit**

```bash
git add seeds/seed_predictions.py
git commit -m "feat: bulk prediction seed script with Match 1 data"
```

---

## Task 11: ngrok + LINE Setup

- [ ] **Step 1: Install ngrok**

```bash
brew install ngrok
ngrok config add-authtoken YOUR_NGROK_TOKEN
```
Get token from ngrok.com (free account).

- [ ] **Step 2: Create LINE Official Account**

1. Go to developers.line.biz → Create Provider → Create Channel → Messaging API
2. Set channel name (e.g. "WC2026Bot")
3. Under **Messaging API** tab:
   - Issue Channel Access Token (long-lived) → copy to `config.json`
   - Copy Channel Secret → copy to `config.json`
   - Disable **Auto-reply messages**
   - Disable **Greeting messages**

- [ ] **Step 3: Start tunnel and set webhook**

```bash
ngrok http 8000
```
Copy the `https://xxxx.ngrok.io` URL.

In LINE Developers Console → Messaging API → Webhook URL:
```
https://xxxx.ngrok.io/webhook
```
Click **Verify** → expect green checkmark.

- [ ] **Step 4: Get your admin LINE user ID**

```bash
python bot.py
```
Send any message to the bot (1-on-1). Check terminal logs — bot will log your `userId`.
Copy it to `config.json` as `ADMIN_LINE_USER_ID`.

- [ ] **Step 5: Add bot to group**

In LINE app → QR code from bot profile → share with group → add as member.

- [ ] **Step 6: Test in group**

Send `/help` → bot should reply with command list.
Send `/stand` → should show current standings with Match 1 data.

---

## Task 12: End-to-End Verification

- [ ] **Step 1: Verify parser with real chat examples**

```bash
python -c "
import json
from parser import parse_predictions
teams = json.load(open('teams.json'))
tests = [
    'บราซิล 2:1 ญี่ปุ่น',
    'เยอรมนี 2–0ปารากวัย',
    'เนเธอร์แลนด์ 1 – 0โมร็อกโก',
    'บราซิล 1:1 ญี่ปุ่น\nเยอรมัน 2:0 ปารากวัย\nเนเธอแลนด์ 0:1 โมรอคโค',
]
for t in tests:
    print(repr(t[:30]), '->', parse_predictions(t, teams))
"
```
Expected: all parse correctly.

- [ ] **Step 2: Verify standings match session calculation**

```bash
sqlite3 worldcup.db "
SELECT p.line_display_name, COALESCE(SUM(pr.points),0) as pts
FROM players p LEFT JOIN predictions pr ON p.id=pr.player_id
GROUP BY p.id ORDER BY pts DESC;"
```
Expected: Nuttapon Momo, Khomkrit(Benz), saravuts_เอ = 2pts each.

- [ ] **Step 3: Test /result today in group**

Post `/result today` in LINE group. Bot should show today's 3 matches with all submitted predictions.

- [ ] **Step 4: Test unsend**

1. Post a prediction in 1-on-1 with bot (before deadline)
2. Unsend the message
3. Check DB: `sqlite3 worldcup.db "SELECT * FROM predictions ORDER BY id DESC LIMIT 1;"`
4. Prediction should be deleted.

- [ ] **Step 5: Test /sync**

Post `/sync` in group (as admin). Bot should fetch results from football-data.org and reply with any new results.

---

## v2 Notes (Deferred)

- Double/Rev mechanic — add `doublerev` table once rules confirmed
- Buy/sell points — add `point_transactions` table
- Round of 16+ schedule — add via `/seed_match` admin command or extend `seeds/init_db.py`
- EC2 migration if ngrok uptime is problem
