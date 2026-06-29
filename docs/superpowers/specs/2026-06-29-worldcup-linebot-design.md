# World Cup 2026 LINE Bot — Design Spec
Date: 2026-06-29

## Overview

LINE group bot for "World Cup 2026" — 17-player prediction pool. Tracks predictions, fetches real match results, calculates standings. Local Flask server exposed via ngrok. Personal HTML dashboard for admin view.

---

## Context

- 17 players, 3,000 THB each, 51,000 THB prize pool
- Predictions posted as free-text in LINE group (Thai/English mix)
- Match results fetched from football-data.org API
- Admin: Thomas Clover (LINE user ID hardcoded in config)
- v1 scope: predictions, scoring, standings, commands, dashboard
- v2 deferred: Double/Rev, buy/sell point mechanics

---

## Architecture

```
LINE Group
    │ webhook (every message)
    ▼
Flask app (bot.py)
    ├── Message Parser     — strict regex, extracts predictions
    ├── Command Handler    — /stand /result /seed /sync /help
    ├── Scoring Engine     — rules loaded from scoring_rules.json
    ├── Result Fetcher     — football-data.org API
    ├── SQLite DB          — predictions, players, matches
    └── HTML Dashboard     — localhost:8000/dashboard (manual refresh)
```

---

## Setup & Deployment

### 1. LINE Official Account + Messaging API

1. Go to [LINE Developers Console](https://developers.line.biz/)
2. Create a Provider → Create a new channel → **Messaging API**
3. Note down:
   - `CHANNEL_SECRET`
   - `CHANNEL_ACCESS_TOKEN` (issue a long-lived token)
4. Under Messaging API settings:
   - **Disable** auto-reply messages
   - **Disable** greeting message
   - **Enable** "Use webhook"
5. Add bot to LINE group: share bot's QR code or invite link → add as group member

### 2. Local server + ngrok

```bash
# Terminal 1 — tunnel
ngrok http 8000
# Copy the https URL e.g. https://abc123.ngrok.io

# LINE Developers Console → Messaging API → Webhook URL:
# https://abc123.ngrok.io/webhook
# Click "Verify" — should return 200 OK

# Terminal 2 — bot
python bot.py
```

### 3. Config file

```json
// config.json
{
  "LINE_CHANNEL_SECRET": "xxx",
  "LINE_CHANNEL_ACCESS_TOKEN": "xxx",
  "FOOTBALL_DATA_API_KEY": "xxx",
  "ADMIN_LINE_USER_ID": "Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "DB_PATH": "worldcup.db"
}
```

Admin LINE user ID found in webhook payload when you send a message — bot logs it on first run.

### 4. Startup sequence (each match day)

```bash
ngrok http 8000                    # start tunnel
# update webhook URL in LINE console if ngrok URL changed
python bot.py                      # start bot
# verify with /help in LINE group
```

---

## Database Schema

```sql
players (
  id INTEGER PRIMARY KEY,
  line_display_name TEXT UNIQUE NOT NULL,
  aliases TEXT  -- JSON array e.g. ["thomas","โทมัส","tom"]
)

matches (
  id INTEGER PRIMARY KEY,
  match_date_ict TEXT NOT NULL,    -- YYYY-MM-DD ICT
  kickoff_utc TEXT NOT NULL,       -- ISO datetime UTC
  deadline_ict TEXT NOT NULL,      -- YYYY-MM-DD 15:00:00 ICT (day before match_date_ict)
  home_team_en TEXT NOT NULL,
  away_team_en TEXT NOT NULL,
  home_team_th TEXT,
  away_team_th TEXT,
  home_score INTEGER,              -- NULL until result fetched
  away_score INTEGER,
  round TEXT NOT NULL              -- "32","16","8","4","final"
)

predictions (
  id INTEGER PRIMARY KEY,
  player_id INTEGER REFERENCES players(id),
  match_id INTEGER REFERENCES matches(id),
  home_pred INTEGER NOT NULL,
  away_pred INTEGER NOT NULL,
  line_message_id TEXT,            -- for unsend handling
  submitted_at TEXT NOT NULL,      -- ISO datetime ICT
  points INTEGER,                  -- NULL until scored
  UNIQUE(player_id, match_id)      -- last write wins on conflict
)
```

---

## Configuration Files

### `players.json`
```json
[
  {
    "line_display_name": "Thomas Clover",
    "aliases": ["thomas", "tom", "โทมัส"]
  },
  {
    "line_display_name": "Kritsana Th.",
    "aliases": ["kritsana", "กฤษณะ", "นา"]
  }
]
```
Bot reloads on every request — no restart needed after editing.

### `scoring_rules.json`
```json
{
  "32": {"exact": 2, "correct": 1, "wrong": 0},
  "16": {"exact": 4, "correct": 2, "wrong": 0},
  "8":  {"exact": 6, "correct": 3, "wrong": 0},
  "4":  {"exact": 8, "correct": 4, "wrong": 0},
  "final": {"exact": 8, "correct": 4, "wrong": 0}
}
```

### `teams.json`
Thai→English team name mapping. All spelling variants included.
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
  "แคนาดา": "Canada"
}
```
All 32 knockout teams seeded before bot goes live.

---

## Match Schedule (Round of 32, ICT)

| ICT Date | Kickoff ICT | Match | Deadline ICT |
|----------|------------|-------|--------------|
| 28/06 | 23:00 | South Africa vs Canada | 28/06 15:00 |
| 30/06 | 00:00 | Brazil vs Japan | 29/06 15:00 |
| 30/06 | 03:30 | Germany vs Paraguay | 29/06 15:00 |
| 30/06 | 08:00 | Netherlands vs Morocco | 29/06 15:00 |
| 01/07 | 00:00 | Ivory Coast vs Norway | 30/06 15:00 |
| 01/07 | 04:00 | France vs Sweden | 30/06 15:00 |
| 01/07 | 08:00 | Mexico vs Ecuador | 30/06 15:00 |
| 02/07 | 23:00 | England vs Congo DR | 01/07 15:00 |
| 03/07 | 02:00 | USA vs Bosnia | 02/07 15:00 |
| 03/07 | TBD | Belgium vs TBD | 02/07 15:00 |
| 03/07 | 04:00 | Spain vs Austria | 02/07 15:00 |
| 04/07 | 01:00 | Australia vs Egypt | 03/07 15:00 |
| 04/07 | 02:00 | Portugal vs Croatia | 03/07 15:00 |
| 04/07 | 06:00 | Switzerland vs Algeria | 03/07 15:00 |
| 05/07 | 05:00 | Argentina vs Cape Verde | 04/07 15:00 |
| 05/07 | 08:30 | Colombia vs Ghana | 04/07 15:00 |

All matches on same ICT date share one deadline: **15:00 ICT the prior day**.

---

## Message Parser

**Prediction pattern (strict):**
```
<team> \s* (\d+) \s* [:\-–] \s* (\d+) \s* <team>
```
Separators: `:`, `-` (hyphen), `–` (en-dash U+2013). Optional spaces around separator and between score and team name. Digits only. Team names from `teams.json` (Thai or English).

Real examples that must parse:
- `บราซิล 1–0 ญี่ปุ่น` — en-dash
- `เยอรมนี 2–0ปารากวัย` — no space between score and team
- `เนเธอร์แลนด์ 1 – 0โมร็อกโก` — spaces around dash, no space before team

**Multi-match message:** Parse all lines. Last parsed prediction for a given match overwrites earlier one in same message.

**Flow:**
1. Tokenize each line
2. Match team names via `teams.json` (case-insensitive for English)
3. Lookup match in DB by team pair (order-insensitive)
4. Check deadline: `now_ict < match.deadline_ict` → accept; else reply deadline passed
5. Store with `line_message_id`, overwrite on `UNIQUE(player_id, match_id)` conflict

**Non-prediction lines:** Ignored silently.
**`/`-prefixed messages:** Routed to command handler, not parser.

---

## Unsend Handling

LINE sends `message.unsend` webhook event with original `message_id`.

1. Lookup prediction by `line_message_id`
2. If match not yet kicked off → delete prediction (silent, no group reply)
3. If match already kicked off → ignore (prediction locked)

Player re-sends after unsend → treated as fresh prediction.

---

## Player Name Resolution

**Lookup order:**
1. Exact match on `line_display_name`
2. Case-insensitive match on any alias in `players.json`
3. Multiple matches → reply listing candidates, ask to be more specific
4. No match → reply with full player list + notify admin

**`/seed` rule:** Must resolve to exactly 1 player. No write on ambiguity.

**Unknown player posts prediction:** Bot sends admin notification. Admin adds player to `players.json` manually.

---

## Commands

### `/stand` or `/table`
```
🏆 ตารางคะแนน World Cup 2026
(อัพเดท: 29/06/2026)

1.  Nuttapon Momo   ⭐ 2 แต้ม
1.  Khomkrit(Benz)  ⭐ 2 แต้ม
1.  saravuts_เอ     ⭐ 2 แต้ม
—
4.  Thomas Clover   1 แต้ม
...
16. Trisit Bobby    0 แต้ม
```
Ties shown at same rank. No tiebreaker — group decides manually.

### `/result [player]`
Full prediction history for named player, grouped by date.
```
📊 Thomas Clover — ประวัติการทาย

📅 28/06/2026
แอฟริกาใต้ vs แคนาดา
  ทาย: 0-2  |  จริง: 0-1  |  ✅ 1 แต้ม

📅 29/06/2026
บราซิล vs ญี่ปุ่น
  ทาย: 1-0  |  จริง: ⏳  |  —
...
รวม: 1 แต้ม (1 นัด)
```

### `/result me`
Same as `/result [player]` but resolved from the LINE user ID who sent the command. No argument needed. Bot fetches requester's display name via LINE profile API, resolves to player, returns their own history. If unresolved → reply error with player list.

### `/result YYYY-MM-DD`
All players' predictions for matches on a specific ICT date (not necessarily today). Same format as `/result today` but for the given date.
```
📅 ผลการทาย 30/06/2026

⚽ บราซิล vs ญี่ปุ่น
  จริง: 1-0
  Thomas Clover   1-0  ✅ 2 แต้ม
  ...
```
Invalid date format → reply error.

### `/result today`
All players' predictions for today's ICT-date matches.
```
📅 ผลการทาย 29/06/2026

⚽ บราซิล vs ญี่ปุ่น
  จริง: ⏳ รอผล
  Thomas Clover   1-0
  Kritsana Th.    2-1
  ...
```
After `/sync`: actual score shown, each player gets ✅/❌ + points.

### `/seed [player] [date] [home] [score] [away]`
Admin-only. Backfills or overwrites one prediction.
```
/seed thomas 2026-06-28 "South Africa" 0-2 Canada
```
Reply confirms player, match, score, overwrite status.
Non-admin → silently ignored.

### `/sync`
Admin-only. Fetches latest results from football-data.org, recalculates all points.
```
🔄 กำลังดึงผลการแข่งขัน...
✅ บราซิล 2-1 ญี่ปุ่น
✅ เยอรมัน 2-0 ปารากวัย
✅ เนเธอร์แลนด์ 1-1 โมร็อกโก
📊 คำนวณคะแนนเสร็จแล้ว — อัพเดท 3 นัด, 17 ผู้เล่น
พิมพ์ /stand เพื่อดูตาราง
```

### `/help`
Lists all commands with one-line Thai description. Includes `/result me` and `/result YYYY-MM-DD`.

---

## Scoring Engine

```python
def score(predicted: tuple, actual: tuple, round: str) -> int:
    rules = load_rules()[round]
    if predicted == actual:
        return rules["exact"]
    if sign(predicted[0] - predicted[1]) == sign(actual[0] - actual[1]):
        return rules["correct"]
    return rules["wrong"]
```

Recalculated on every `/sync`. Stored in `predictions.points`.

---

## Result Fetcher

- API: football-data.org free tier
- Triggered by `/sync` only — no background polling
- Maps API English team names → DB team names
- Updates `home_score`, `away_score` in `matches`
- Recalculates all `predictions.points` for completed matches

---

## HTML Dashboard (`localhost:8000/dashboard`)

Manual refresh. Four sections:
1. **Standings** — full leaderboard with points, tied ranks shown
2. **Match Schedule** — all matches, kickoff ICT, result or ⏳, deadline
3. **Today's Predictions** — all players' picks for today's ICT-date matches
4. **Player Detail** — click any player → full history grouped by date

Served by same Flask app. Local only, no auth.

---

## File Structure

```
worldcup.db
bot.py                  # Flask app, webhook + command routing
parser.py               # Prediction regex parser
scoring_engine.py       # Points calculation
result_fetcher.py       # football-data.org client
db.py                   # SQLite helpers
config.json             # Secrets + admin user ID
players.json            # Player aliases (editable, hot-reload)
teams.json              # Thai/English team name mapping
scoring_rules.json      # Points per round (editable, hot-reload)
seeds/
  matches.sql           # Round of 32 schedule seed
  predictions_day0.sql  # Past predictions seed (Match 1)
dashboard/
  index.html
test_parser.py
test_scoring.py
```

---

## Testing Plan

1. **`test_parser.py`** — valid formats (`2:1`, `2-1`), invalid (`2 1`, `2/1`, plain text), Thai names, multi-line last-wins
2. **`test_scoring.py`** — exact/correct/wrong for each round, edge cases (0-0 draw correct, 1-0 vs 2-0)
3. **Deadline logic** — before 15:00 accepted, after kickoff rejected, exactly at 15:00
4. **Webhook simulator** — LINE developer console sends fake payloads to ngrok
5. **1-on-1 LINE staging** — all commands tested personally before adding to group
6. **Seed + sync dry run** — load Match 1 data, `/sync`, verify standings match manual calculation in this session

**Go-live gate:**
- Parser handles all real prediction formats from existing chat log ✅
- Standings after seed match manual standings (Nuttapon/Khomkrit/saravuts = 2pts, rest = 1pt, Trisit/Trinity = 0pt) ✅
- Unsend tested in 1-on-1 chat ✅

---

## v2 (Deferred)

- Double/Rev mechanic (rules TBD — procure from group)
- Buy/sell point mechanic (rules TBD)
- Round of 16+ schedule (seeded as bracket resolves)
- ngrok → EC2 migration if uptime becomes issue
