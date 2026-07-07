# Double/Rev Mechanic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the admin flag a player's existing prediction as "doubled" (×2 if correct, -2 if wrong), capped per round, via a new `/double` LINE command, with visibility in `/result` and `/stand`.

**Architecture:** One new `predictions.doubled` column (migrated in `db.py:init_schema`), a `double_cap` field added to each round in `scoring_rules.json`, a `doubled` parameter threaded through `scoring.py:score_prediction`/`recalculate_all`, a new `/double` branch in `commands.py:handle_command` mirroring the existing `/setscore`/`/seed` admin-command pattern, and small additions to the `/result` and `/stand` text builders.

**Tech Stack:** Python 3.9, sqlite3, Flask, pytest. No new dependencies.

## Global Constraints

- Double is per-match, not per-day.
- Caps per round: 32→0, 16→2, 8 (QF)→1, 4 (SF)→1, final→0.
- Cap enforcement counts existing `doubled=1` predictions for that player within that round — no separate quota table.
- `/double` is admin-only, same silent-ignore behavior as `/seed`/`/setscore` for non-admins.
- Activating double requires an existing prediction for that match; must be before that match's `deadline_ict` (same deadline as normal predictions).
- Re-running `/double` on an already-doubled prediction toggles it off (refunds quota).
- Wrong-but-doubled must score exactly `-2`, never `wrong * 2` (since `wrong` is 0).
- `/stand` marker (🔥) shows for the whole current round (pending or resolved), not just while pending.

---

## Task 1: DB migration — `predictions.doubled` column + data-access helpers

**Files:**
- Modify: `db.py:19-56` (`init_schema`), append new functions after `get_today_predictions` (`db.py:177-189`)
- Test: `test_db.py`

**Interfaces:**
- Produces: `db.get_prediction(conn, player_id, match_id) -> Optional[sqlite3.Row]` (row includes `doubled` column)
- Produces: `db.set_doubled(conn, prediction_id: int, value: int) -> None`
- Produces: `db.count_doubled_in_round(conn, player_id: int, round_val: str) -> int`
- Produces: `db.get_current_round(conn) -> Optional[str]`
- Produces: `db.has_doubled_in_round(conn, round_val: str) -> set[str]` (set of `line_display_name`)
- Consumes: existing `sqlite3.Row` factory set in `db.get_db`

- [ ] **Step 1: Write failing tests for the migration and new helpers**

```python
# test_db.py — add below existing test_schema_creates_tables

import db as dbmod


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest test_db.py -v`
Expected: FAIL — `sqlite3.OperationalError: no such column: doubled` and `AttributeError: module 'db' has no attribute 'get_prediction'` (etc.)

- [ ] **Step 3: Add the migration and helpers**

In `db.py`, modify `init_schema` (replace lines 19-56):

```python
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
```

Append at the end of `db.py` (after `get_today_predictions`):

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest test_db.py -v`
Expected: PASS (all tests including the new ones)

- [ ] **Step 5: Commit**

```bash
git add db.py test_db.py
git commit -m "feat(db): add predictions.doubled column and double-mechanic helpers"
```

---

## Task 2: Scoring engine — `doubled` parameter + `double_cap` config

**Files:**
- Modify: `scoring.py:11-44` (`score_prediction`, `recalculate_all`)
- Modify: `scoring_rules.json`
- Test: `test_scoring.py`

**Interfaces:**
- Consumes: `predictions.doubled` column from Task 1
- Produces: `scoring.score_prediction(predicted, actual, round, rules, doubled=False) -> int`
- Produces: `scoring.recalculate_all(conn, rules)` now reads and applies `doubled` per row (same signature as before)

- [ ] **Step 1: Write failing tests**

```python
# test_scoring.py — add below existing tests, and update RULES to include double_cap

RULES = {
    "32":    {"exact": 2, "correct": 1, "wrong": 0, "double_cap": 0},
    "16":    {"exact": 4, "correct": 2, "wrong": 0, "double_cap": 2},
    "8":     {"exact": 6, "correct": 3, "wrong": 0, "double_cap": 1},
    "4":     {"exact": 8, "correct": 4, "wrong": 0, "double_cap": 1},
    "final": {"exact": 8, "correct": 4, "wrong": 0, "double_cap": 0},
}


def test_doubled_exact_score():
    assert score_prediction((2, 1), (2, 1), "16", RULES, doubled=True) == 8


def test_doubled_correct_result_only():
    assert score_prediction((3, 1), (2, 1), "16", RULES, doubled=True) == 4


def test_doubled_wrong_is_minus_two_not_zero():
    assert score_prediction((0, 1), (1, 0), "16", RULES, doubled=True) == -2


def test_not_doubled_defaults_unchanged():
    assert score_prediction((2, 1), (2, 1), "16", RULES) == 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest test_scoring.py -v`
Expected: FAIL — `TypeError: score_prediction() got an unexpected keyword argument 'doubled'`

- [ ] **Step 3: Update `scoring.py`**

Replace `scoring.py:11-44`:

```python
def score_prediction(
    predicted: tuple,
    actual: tuple,
    round: str,
    rules: dict,
    doubled: bool = False,
) -> int:
    r = rules[round]
    if predicted == actual:
        pts = r["exact"]
    elif _result(*predicted) == _result(*actual):
        pts = r["correct"]
    else:
        pts = r["wrong"]
    if doubled:
        pts = pts * 2 if pts > 0 else -2
    return pts


def recalculate_all(conn: sqlite3.Connection, rules: dict):
    """Recalculate points for all predictions where match result is known."""
    rows = conn.execute("""
        SELECT p.id, p.home_pred, p.away_pred, p.doubled,
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
            rules,
            doubled=bool(row["doubled"]),
        )
        conn.execute("UPDATE predictions SET points = ? WHERE id = ?", (pts, row["id"]))

    conn.commit()
```

Replace `scoring_rules.json` in full:

```json
{
  "32":    {"exact": 2, "correct": 1, "wrong": 0, "double_cap": 0},
  "16":    {"exact": 4, "correct": 2, "wrong": 0, "double_cap": 2},
  "8":     {"exact": 6, "correct": 3, "wrong": 0, "double_cap": 1},
  "4":     {"exact": 8, "correct": 4, "wrong": 0, "double_cap": 1},
  "final": {"exact": 8, "correct": 4, "wrong": 0, "double_cap": 0}
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest test_scoring.py -v`
Expected: PASS (all tests, including pre-existing ones — pre-existing tests use a local `RULES` dict in that file too; verify it still has `double_cap` keys added so no `KeyError` if any code path reads it, though `score_prediction` only reads `double_cap` from `rules` indirectly via commands.py, not in scoring.py itself)

- [ ] **Step 5: Commit**

```bash
git add scoring.py scoring_rules.json test_scoring.py
git commit -m "feat(scoring): support doubled predictions (x2 correct, -2 wrong)"
```

---

## Task 3: `/double` command

**Files:**
- Modify: `commands.py:1-20` (imports — add `from datetime import datetime, timezone, timedelta` already present; no new imports needed), `commands.py:103-120` (`_help_text`), `commands.py:449` (append new command branch before final `return None`)
- Test: manual/integration — covered by Task 4's display tests plus a focused unit test file

**Interfaces:**
- Consumes: `db.resolve_player`, `db.get_player_id`, `db.get_match_by_teams`, `db.get_prediction`, `db.set_doubled`, `db.count_doubled_in_round` (Task 1), `scoring.recalculate_all` (Task 2), `rules[round]["double_cap"]` (Task 2)
- Produces: `/double <player> <team1> <team2>` command branch in `commands.handle_command`

- [ ] **Step 1: Write failing test**

Create `test_commands_double.py`:

```python
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


def _setup(round_val="16", deadline_passed=False):
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    path = f.name
    f.close()
    conn = db.get_db({"DB_PATH": path})
    db.init_schema(conn)
    deadline = (datetime.now(ICT) - timedelta(hours=1)) if deadline_passed else (datetime.now(ICT) + timedelta(hours=1))
    conn.execute("""
        INSERT INTO matches
        (match_date_ict, kickoff_utc, deadline_ict, home_team_en, away_team_en,
         home_team_th, away_team_th, round)
        VALUES ('2026-07-08', '2026-07-08T16:00:00Z', ?, 'Argentina', 'Egypt',
                'อาร์เจนตินา', 'อียิปต์', ?)
    """, (deadline.strftime("%Y-%m-%dT%H:%M:%S"), round_val))
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


def test_double_rejects_after_deadline():
    conn, path = _setup(round_val="16", deadline_passed=True)
    try:
        resp = commands.handle_command(
            "/double kritsana อาร์เจนตินา อียิปต์", "Uadmin", conn, CONFIG, PLAYERS, RULES, TEAMS
        )
        assert "เลยเวลา" in resp
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest test_commands_double.py -v`
Expected: FAIL — `/double` falls through to `return None` at end of `handle_command`, so responses are `None` instead of the expected strings.

- [ ] **Step 3: Implement `/double` in `commands.py`**

Insert this new branch into `commands.py` right before the final `return None` (currently line 449), i.e. after the `/template` branch:

```python
    if cmd == "/double":
        if not _is_admin(user_id, config):
            return None
        if len(parts) != 4:
            return "❌ รูปแบบ: /double [ชื่อ] [ทีมเหย้า] [ทีมเยือน]"
        player_arg, team1_arg, team2_arg = parts[1], parts[2], parts[3]

        name, candidates = db.resolve_player(player_arg, players)
        if not name:
            if candidates:
                return "❌ ชื่อตรงกับหลายคน: " + ", ".join(candidates)
            return f"❌ ไม่พบผู้เล่น '{player_arg}'"

        team1_en = teams.get(team1_arg) or (team1_arg if team1_arg in teams.values() else None)
        team2_en = teams.get(team2_arg) or (team2_arg if team2_arg in teams.values() else None)
        if not team1_en:
            return f"❌ ไม่พบทีม '{team1_arg}'"
        if not team2_en:
            return f"❌ ไม่พบทีม '{team2_arg}'"

        match_row = db.get_match_by_teams(conn, team1_en, team2_en)
        if not match_row:
            return f"❌ ไม่พบนัด {team1_en} vs {team2_en}"

        player_id = db.get_player_id(conn, name)
        pred_row = db.get_prediction(conn, player_id, match_row["id"])
        if not pred_row:
            return f"❌ {name} ยังไม่ได้ทายนัดนี้ ทายก่อนถึงจะ double ได้"

        deadline = datetime.fromisoformat(
            match_row["deadline_ict"].replace("Z", "+00:00")
        ).astimezone(ICT)
        if datetime.now(ICT) > deadline:
            return "❌ เลยเวลากำหนดแล้ว double ไม่ได้"

        home_th = match_row["home_team_th"] or team1_en
        away_th = match_row["away_team_th"] or team2_en
        round_val = match_row["round"]

        if pred_row["doubled"]:
            db.set_doubled(conn, pred_row["id"], 0)
            scoring.recalculate_all(conn, rules)
            return f"✅ ยกเลิก double แล้ว: {name} — {home_th} vs {away_th}"

        cap = rules.get(round_val, {}).get("double_cap", 0)
        used = db.count_doubled_in_round(conn, player_id, round_val)
        if used >= cap:
            return f"❌ {name} ใช้ double ครบโควต้ารอบนี้แล้ว ({used}/{cap})"

        db.set_doubled(conn, pred_row["id"], 1)
        scoring.recalculate_all(conn, rules)
        return (
            f"🔥 เปิด double แล้ว: {name} — {home_th} vs {away_th}\n"
            f"เหลือโควต้า double รอบนี้ {cap - used - 1}/{cap}"
        )
```

Also update `_help_text` (`commands.py:103-120`) — insert this line right after the `/setscore` line:

```python
        "/double [ชื่อ] [ทีมเหย้า] [ทีมเยือน] — เปิด/ปิด double (admin, x2 ถ้าถูก, -2 ถ้าผิด)\n"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest test_commands_double.py -v`
Expected: PASS (all 6 tests)

- [ ] **Step 5: Commit**

```bash
git add commands.py test_commands_double.py
git commit -m "feat(commands): add admin-only /double command"
```

---

## Task 4: `/result` and `/stand` display updates

**Files:**
- Modify: `db.py` — `get_player_history` (`db.py:164-174`) to include `pr.doubled`
- Modify: `commands.py` — `_result_player_text` (`commands.py:36-68`), `_standings_text` (`commands.py:20-33`)
- Test: `test_commands_display.py`

**Interfaces:**
- Consumes: `db.get_current_round`, `db.has_doubled_in_round` (Task 1)
- Produces: updated text output only — no new function signatures

- [ ] **Step 1: Write failing tests**

Create `test_commands_display.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest test_commands_display.py -v`
Expected: FAIL — `🔥x2` and `🔥`/footer text absent from current output

- [ ] **Step 3: Update `db.py:get_player_history`**

Replace `db.py:164-174`:

```python
def get_player_history(conn: sqlite3.Connection, player_id: int) -> list:
    return conn.execute("""
        SELECT m.match_date_ict, m.home_team_th, m.away_team_th,
               m.home_team_en, m.away_team_en,
               m.home_score, m.away_score,
               pr.home_pred, pr.away_pred, pr.points, pr.doubled
        FROM predictions pr
        JOIN matches m ON pr.match_id = m.id
        WHERE pr.player_id = ?
        ORDER BY m.kickoff_utc
    """, (player_id,)).fetchall()
```

- [ ] **Step 4: Update `_result_player_text` in `commands.py`**

Replace `commands.py:36-68`:

```python
def _result_player_text(conn: sqlite3.Connection, player_id: int, display_name: str) -> str:
    rows = db.get_player_history(conn, player_id)
    if not rows:
        return f"ไม่พบประวัติการทายของ {display_name}"

    lines = [f"📊 {display_name} — ประวัติการทาย", ""]
    current_date: Optional[str] = None
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
        double_marker = " 🔥x2" if row["doubled"] else ""
        actual = (f"{row['home_score']}-{row['away_score']}"
                  if row["home_score"] is not None else "⏳")
        pts = row["points"]
        if pts is not None:
            check = "✅" if pts >= 0 else "❌"
            pts_str = f"{check} {pts} แต้ม"
        else:
            pts_str = "—"
        lines.append(f"{home_th} vs {away_th}")
        lines.append(f"  ทาย: {pred}{double_marker}  |  จริง: {actual}  |  {pts_str}")

        if pts is not None:
            total_pts += pts
            match_count += 1

    lines.append("")
    lines.append(f"รวม: {total_pts} แต้ม ({match_count} นัด)")
    return "\n".join(lines)
```

(Note: `check = "✅" if pts >= 0 else "❌"` replaces the previous hardcoded `"✅"` since doubled-wrong now scores `-2` and must render as ❌, not ✅.)

- [ ] **Step 5: Update `_standings_text` in `commands.py`**

Replace `commands.py:20-33`:

```python
def _standings_text(conn: sqlite3.Connection) -> str:
    rows = db.get_standings(conn)
    current_round = db.get_current_round(conn)
    doubled_names = db.has_doubled_in_round(conn, current_round) if current_round else set()
    today = datetime.now(ICT).strftime("%d/%m/%Y")
    lines = [f"🏆 ตารางคะแนน World Cup 2026", f"(อัพเดท: {today})", ""]
    rank = 1
    prev_pts: Optional[int] = None
    for i, row in enumerate(rows):
        pts = row["total_points"]
        if pts != prev_pts:
            rank = i + 1
            prev_pts = pts
        star = " ⭐" if pts > 0 and rank == 1 else ""
        flame = " 🔥" if row["line_display_name"] in doubled_names else ""
        lines.append(f"{rank:2}. {row['line_display_name']:<22} {pts} แต้ม{star}{flame}")
    if doubled_names:
        lines.append("")
        lines.append("🔥 = ใช้ double ในรอบนี้แล้ว")
    return "\n".join(lines)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest test_commands_display.py test_scoring.py test_db.py test_commands_double.py -v`
Expected: PASS (all tests across all four files)

- [ ] **Step 7: Run the full test suite**

Run: `pytest -v`
Expected: PASS (no regressions in `test_parser.py`, `test_template.py`)

- [ ] **Step 8: Commit**

```bash
git add db.py commands.py test_commands_display.py
git commit -m "feat(display): show double marker in /result and /stand"
```

---

## Task 5: Deploy migration to live `worldcup.db`

**Files:**
- None (operational step, no code change)

**Interfaces:**
- Consumes: `db.init_schema` (Task 1), already called on every webhook request in `bot.py` — actually check: `bot.py` does NOT call `init_schema` on every request currently. Confirm before this task whether `init_schema` runs at process startup or needs a one-off manual run against `worldcup.db`.

- [ ] **Step 1: Check whether `init_schema` runs automatically**

Run: `grep -n "init_schema" bot.py`
If it prints nothing, `init_schema` is not called automatically — proceed to Step 2. If it is called on startup, skip to Step 3.

- [ ] **Step 2: Manually run the migration against the live DB**

```bash
python3 -c "import db, json; conn = db.get_db(json.load(open('config.json'))); db.init_schema(conn); conn.close()"
```

Expected: no output, exits 0. Verify:

```bash
sqlite3 worldcup.db "PRAGMA table_info(predictions)" | grep doubled
```

Expected: a row showing the `doubled` column.

- [ ] **Step 3: Restart the bot process** (per `docs/server.md` restart instructions) so the running process picks up the new `commands.py`/`scoring.py`/`db.py` code.

- [ ] **Step 4: Smoke test in LINE group**

Send `/help` as admin — confirm the new `/double` line appears. Send `/double <player> <team1> <team2>` for a real pending match — confirm the 🔥 confirmation reply and correct quota count.
