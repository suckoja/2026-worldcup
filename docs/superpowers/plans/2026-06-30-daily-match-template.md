# Daily Match Template Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Send a daily match prediction template to the LINE group at 6 AM ICT, and provide `/setgroup` + `/sendtemplate` admin commands for setup and manual testing.

**Architecture:** Add two admin commands to `commands.py` (`/setgroup` saves group ID to config, `/sendtemplate` pushes today's template immediately). Extract template-building logic into `template.py`. Create `send_template.py` standalone script for cron.

**Tech Stack:** Python 3, LINE Bot SDK v3, SQLite, system cron

## Global Constraints

- No new pip dependencies
- Thai team names (`home_team_th`) used in template — fall back to `home_team_en` if null
- Admin check: `user_id == config["ADMIN_LINE_USER_ID"]`
- All times in ICT (UTC+7)
- `LINE_GROUP_ID` stored in `config.json` at runtime

---

### Task 1: Extract template builder into `template.py`

**Files:**
- Create: `template.py`
- Test: `test_template.py`

**Interfaces:**
- Produces: `build_template(matches: list[sqlite3.Row]) -> str`
  - `matches`: rows with fields `home_team_th`, `away_team_th`, `home_team_en`, `away_team_en`, `kickoff_utc` ordered by `kickoff_utc`
  - Returns formatted string ready to push to LINE

- [ ] **Step 1: Write the failing test**

```python
# test_template.py
import sqlite3
from template import build_template

def _row(home_th, away_th, home_en, away_en):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE m (home_team_th, away_team_th, home_team_en, away_team_en, kickoff_utc)"
    )
    conn.execute(
        "INSERT INTO m VALUES (?,?,?,?,?)",
        (home_th, away_th, home_en, away_en, "2026-07-01T17:00:00Z")
    )
    return conn.execute("SELECT * FROM m").fetchone()

def test_build_template_thai_names():
    rows = [
        _row("ฝรั่งเศส", "สวีเดน", "France", "Sweden"),
        _row("เม็กซิโก", "เอกวาดอร์", "Mexico", "Ecuador"),
    ]
    result = build_template(rows)
    assert "ฝรั่งเศส 0-0 สวีเดน" in result
    assert "เม็กซิโก 0-0 เอกวาดอร์" in result

def test_build_template_fallback_to_en():
    rows = [_row(None, None, "France", "Sweden")]
    result = build_template(rows)
    assert "France 0-0 Sweden" in result

def test_build_template_header():
    rows = [_row("ฝรั่งเศส", "สวีเดน", "France", "Sweden")]
    result = build_template(rows)
    assert result.startswith("📋 ทายผลวันนี้")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /path/to/project && ./venv/bin/pytest test_template.py -v
```

Expected: `ModuleNotFoundError: No module named 'template'`

- [ ] **Step 3: Implement `template.py`**

```python
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone, timedelta

ICT = timezone(timedelta(hours=7))

_THAI_MONTHS = ["", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
                "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]


def _thai_date(date_str: str) -> str:
    """'2026-07-01' → '1 ก.ค.'"""
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return f"{d.day} {_THAI_MONTHS[d.month]}"


def build_template(matches: list) -> str:
    """Build prediction template string from match rows ordered by kickoff_utc."""
    if not matches:
        return ""
    # Derive date from first match kickoff
    first_kickoff = datetime.fromisoformat(
        matches[0]["kickoff_utc"].replace("Z", "+00:00")
    ).astimezone(ICT)
    date_label = _thai_date(first_kickoff.strftime("%Y-%m-%d"))

    lines = [f"📋 ทายผลวันนี้ ({date_label})", ""]
    for row in matches:
        home = row["home_team_th"] or row["home_team_en"]
        away = row["away_team_th"] or row["away_team_en"]
        lines.append(f"{home} 0-0 {away}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
./venv/bin/pytest test_template.py -v
```

Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add template.py test_template.py
git commit -m "feat: add template builder for daily match predictions"
```

---

### Task 2: Add `/setgroup` command

**Files:**
- Modify: `commands.py` (add handler in `handle_command`)
- Modify: `bot.py` (pass `group_id` to command handler; save to config on success)

**Interfaces:**
- Consumes: `handle_command(text, user_id, conn, config, players, rules, teams, display_name, group_id) -> Optional[str]`
  - Add `group_id: Optional[str] = None` parameter
- Produces: `"/setgroup"` case returns `"__SETGROUP__"` sentinel so `bot.py` can write config

- [ ] **Step 1: Add `group_id` param and `/setgroup` handler in `commands.py`**

In `handle_command` signature, add `group_id: Optional[str] = None` after `display_name`:

```python
def handle_command(
    text: str,
    user_id: str,
    conn: sqlite3.Connection,
    config: dict,
    players: list,
    rules: dict,
    teams: dict,
    display_name: Optional[str] = None,
    group_id: Optional[str] = None,
) -> Optional[str]:
```

Add this case before the `return None` at the end of `handle_command`:

```python
    if cmd == "/setgroup":
        if not _is_admin(user_id, config):
            return None
        if not group_id:
            return "❌ ใช้คำสั่งนี้ในกลุ่มเท่านั้น"
        return "__SETGROUP__"
```

Also update `_help_text()` to add the new commands:

```python
def _help_text() -> str:
    return (
        "คำสั่งที่ใช้ได้:\n"
        "/stand หรือ /table — ตารางคะแนน\n"
        "/result me — ประวัติการทายของตัวเอง\n"
        "/result [ชื่อ] — ประวัติการทายของผู้เล่น\n"
        "/result today — การทายวันนี้ทุกคน\n"
        "/result YYYY-MM-DD — การทายวันที่ระบุ\n"
        "/sync — ดึงผลการแข่งขันล่าสุด (admin)\n"
        "/setscore [ทีมเหย้า] [H-A] [ทีมเยือน] — ใส่ผล 90 นาที สำหรับนัดต่อเวลา/จุดโทษ (admin)\n"
        "/seed [ชื่อ] [YYYY-MM-DD] [ทีมเหย้า] [H-A] [ทีมเยือน] — บันทึกย้อนหลัง (admin)\n"
        "/setgroup — บันทึก group ID สำหรับส่ง template (admin, ใช้ในกลุ่ม)\n"
        "/sendtemplate — ส่ง template วันนี้ทันที (admin)\n"
        "/help — แสดงคำสั่ง"
    )
```

- [ ] **Step 2: Update `bot.py` to pass `group_id` and handle `__SETGROUP__` sentinel**

In the webhook handler, find where `group_id` is extracted from source:

```python
group_id = source.get("groupId")
```

This already exists. Update the command dispatch block to pass `group_id` and handle the sentinel:

```python
if text.startswith("/"):
    response = commands.handle_command(
        text, user_id, conn, config, players, rules, teams,
        display_name=display_name,
        group_id=group_id,
    )
    if response == "__SETGROUP__":
        config["LINE_GROUP_ID"] = group_id
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        response = "✅ บันทึก group แล้ว"
    if response and reply_token:
        reply(reply_token, response, config)
```

- [ ] **Step 3: Add `import json` to `bot.py` if not present**

Check top of `bot.py` — `import json` is already there (line 3). No change needed.

- [ ] **Step 4: Manual test**

Run bot locally, send `/setgroup` from a LINE group as admin. Verify `config.json` now contains `"LINE_GROUP_ID": "C..."`.

- [ ] **Step 5: Commit**

```bash
git add commands.py bot.py
git commit -m "feat: add /setgroup command to capture LINE group ID"
```

---

### Task 3: Add `/sendtemplate` command

**Files:**
- Modify: `commands.py` (add handler)
- Modify: `bot.py` (handle `__SENDTEMPLATE__` sentinel)

**Interfaces:**
- Consumes: `build_template(matches: list) -> str` from `template.py`
- Produces: `"/sendtemplate"` case returns `"__SENDTEMPLATE__"` sentinel so `bot.py` pushes to group

- [ ] **Step 1: Import `template` in `commands.py`**

Add to imports at top of `commands.py`:

```python
import template as tmpl
```

- [ ] **Step 2: Add `/sendtemplate` handler in `commands.py`**

Add this case before `return None` at end of `handle_command`:

```python
    if cmd == "/sendtemplate":
        if not _is_admin(user_id, config):
            return None
        if not config.get("LINE_GROUP_ID"):
            return "❌ ยังไม่ได้ตั้ง group — ใช้ /setgroup ในกลุ่มก่อน"
        today = db.today_ict()
        rows = conn.execute(
            "SELECT home_team_th, away_team_th, home_team_en, away_team_en, kickoff_utc "
            "FROM matches WHERE match_date_ict = ? ORDER BY kickoff_utc",
            (today,)
        ).fetchall()
        if not rows:
            return "ไม่มีแมตช์วันนี้"
        return "__SENDTEMPLATE__"
```

- [ ] **Step 3: Handle `__SENDTEMPLATE__` in `bot.py`**

In the command dispatch block, add handling after `__SETGROUP__`:

```python
    if response == "__SENDTEMPLATE__":
        today = db.today_ict()
        rows = conn.execute(
            "SELECT home_team_th, away_team_th, home_team_en, away_team_en, kickoff_utc "
            "FROM matches WHERE match_date_ict = ? ORDER BY kickoff_utc",
            (today,)
        ).fetchall()
        import template as tmpl
        msg = tmpl.build_template(rows)
        push(config["LINE_GROUP_ID"], msg, config)
        response = "✅ ส่ง template แล้ว"
```

- [ ] **Step 4: Manual test**

Send `/sendtemplate` as admin. Verify group receives template message. Verify reply to sender says `✅ ส่ง template แล้ว`.

- [ ] **Step 5: Commit**

```bash
git add commands.py bot.py
git commit -m "feat: add /sendtemplate command for manual template push"
```

---

### Task 4: Create `send_template.py` cron script

**Files:**
- Create: `send_template.py`

**Interfaces:**
- Consumes: `build_template(matches)` from `template.py`, `today_ict()` from `db.py`
- Produces: standalone executable — exits 0 silently if no matches or no group ID

- [ ] **Step 1: Create `send_template.py`**

```python
#!/usr/bin/env python3
"""Cron script: push today's match template to LINE group at 6 AM ICT."""
from __future__ import annotations

import json
import sqlite3

from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    PushMessageRequest, TextMessage,
)

import db
import template as tmpl


def main() -> None:
    with open("config.json", encoding="utf-8") as f:
        config = json.load(f)

    group_id = config.get("LINE_GROUP_ID")
    if not group_id:
        return

    conn = db.get_db(config)
    today = db.today_ict()
    rows = conn.execute(
        "SELECT home_team_th, away_team_th, home_team_en, away_team_en, kickoff_utc "
        "FROM matches WHERE match_date_ict = ? ORDER BY kickoff_utc",
        (today,)
    ).fetchall()
    conn.close()

    if not rows:
        return

    msg = tmpl.build_template(rows)
    cfg = Configuration(access_token=config["LINE_CHANNEL_ACCESS_TOKEN"])
    with ApiClient(cfg) as api_client:
        MessagingApi(api_client).push_message(
            PushMessageRequest(to=group_id, messages=[TextMessage(text=msg)])
        )


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Manual smoke test**

```bash
cd /path/to/project && ./venv/bin/python send_template.py
```

Expected: template message appears in LINE group (if today has matches and `LINE_GROUP_ID` set).

- [ ] **Step 3: Set up cron**

6 AM ICT = 23:00 UTC (previous calendar day). Edit crontab:

```bash
crontab -e
```

Add line (replace `/path/to/project` with actual path):

```
0 23 * * * cd /path/to/project && ./venv/bin/python send_template.py >> /tmp/send_template.log 2>&1
```

- [ ] **Step 4: Commit**

```bash
git add send_template.py
git commit -m "feat: add send_template.py cron script for daily 6 AM push"
```

---

## Self-Review

**Spec coverage:**
- ✅ Section 1 `/setgroup`: Task 2
- ✅ Section 2 template format: Task 1
- ✅ Section 3 scheduler: Task 4
- ✅ Section 4 `/sendtemplate`: Task 3

**Placeholder scan:** None found.

**Type consistency:** `build_template` used identically in Tasks 1, 3, 4. `today_ict()` from `db` used in Tasks 3, 4. `__SETGROUP__` / `__SENDTEMPLATE__` sentinels consistent between `commands.py` and `bot.py` in Tasks 2, 3.
