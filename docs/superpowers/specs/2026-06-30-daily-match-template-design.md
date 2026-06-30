# Daily Match Prediction Template

**Date:** 2026-06-30

## Overview

Bot sends a daily prediction template to the LINE group at 6 AM ICT on days that have matches scheduled. Users copy the message, edit the scores, and post it back — the existing parser handles the rest.

## Section 1: `/setgroup` Command

- Admin-only: reject if `user_id != config["ADMIN_LINE_USER_ID"]`
- Group-only: reject if webhook source has no `groupId`
- On success: write `LINE_GROUP_ID` to `config.json`, reply `✅ บันทึก group แล้ว`
- Implementation: new case in `commands.py`, config write in `bot.py` webhook handler

## Section 2: Template Format

```
📋 ทายผลวันนี้ (1 ก.ค.)

ไอวอรีโคสต์ 0-0 นอร์เวย์
ฝรั่งเศส 0-0 สวีเดน
เม็กซิโก 0-0 เอกวาดอร์
```

- One line per match, Thai team names (`home_team_th`, `away_team_th`) from DB
- Scores default to `0-0` — user edits before posting
- Header line has no score pattern → parser skips it automatically
- Matches ordered by `kickoff_utc` ascending
- If no matches today → script exits silently, nothing sent

## Section 3: Scheduler (`send_template.py`)

Standalone script in project root:

1. Load `config.json` — exit if `LINE_GROUP_ID` missing
2. Connect DB, query `matches WHERE match_date_ict = today_ict()`
3. If no rows → exit
4. Build template string (Section 2 format)
5. Push to `LINE_GROUP_ID` via LINE Messaging API

**Cron (6 AM ICT = 23:00 UTC previous day):**
```
0 23 * * * cd /path/to/project && ./venv/bin/python send_template.py
```

No new pip dependencies. Idempotent per run (no DB writes). Do not configure cron to retry on failure — LINE delivers duplicate messages if run twice.

## Files Changed

| File | Change |
|------|--------|
| `commands.py` | Add `/setgroup` handler |
| `bot.py` | Save `LINE_GROUP_ID` to config on `/setgroup` success |
| `config.json` | Add `LINE_GROUP_ID` field (written at runtime) |
| `send_template.py` | New standalone scheduler script |
