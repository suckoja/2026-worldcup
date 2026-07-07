# Double/Rev Mechanic — Design Spec
Date: 2026-07-07

## Overview

Adds the "double" (เบิลรี) scoring boost to the World Cup 2026 LINE bot, deferred as v2 in the [original design](2026-06-29-worldcup-linebot-design.md) pending group rules. Rules now confirmed.

---

## Rule

Player flags one existing prediction as "doubled" for a match. On scoring:

- Correct pick (exact or outcome-only) → points **×2**
- Wrong pick → **-2** (not 0)

Applies per-match, not per-day.

---

## Usage Caps (per player, per round)

| Round | Cap |
|-------|-----|
| 32 | 0 |
| 16 | 2 |
| 8 (QF) | 1 |
| 4 (SF) | 1 |
| final | 0 (may change later) |

Cap tracked by counting existing `doubled=1` predictions for that player within that round — no separate quota table.

---

## DB Schema Change

```sql
ALTER TABLE predictions ADD COLUMN doubled INTEGER DEFAULT 0;
```

## `scoring_rules.json` Change

Add `double_cap` per round:

```json
{
  "32":    {"exact": 2, "correct": 1, "wrong": 0, "double_cap": 0},
  "16":    {"exact": 4, "correct": 2, "wrong": 0, "double_cap": 2},
  "8":     {"exact": 6, "correct": 3, "wrong": 0, "double_cap": 1},
  "4":     {"exact": 8, "correct": 4, "wrong": 0, "double_cap": 1},
  "final": {"exact": 8, "correct": 4, "wrong": 0, "double_cap": 0}
}
```

---

## Scoring Engine (`scoring.py`)

```python
def score_prediction(predicted, actual, round, rules, doubled=False):
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
```

`recalculate_all` reads `predictions.doubled` per row and passes it to `score_prediction`. Wrong-but-doubled is explicit `-2`, not `wrong * 2` (since `wrong` is 0 and doubling 0 would silently drop the penalty).

---

## Command: `/double <player> <team1> <team2>`

Admin-only (same pattern as `/seed`, `/setscore`). Non-admin sender → silently ignored.

**Flow:**
1. Resolve player (existing alias lookup from `players.json`)
2. Resolve match by team pair, order-insensitive (existing team lookup from `teams.json`)
3. No prediction exists yet for that player+match → reject: `ทายก่อนถึงจะ double ได้`
4. Past deadline (`now_ict >= match.deadline_ict`, same deadline as normal predictions) → reject: `เลยเวลากำหนดแล้ว`
5. Already `doubled=1` on that prediction → **toggle off** (set `doubled=0`, refunds quota), reply confirmation
6. Else check quota: count of `doubled=1` predictions for this player where `match.round` equals this match's round, compared to `double_cap` for that round
   - At cap → reject: `ใช้ double ครบโควต้ารอบนี้แล้ว (n/n)`
   - Under cap → set `doubled=1`, reply confirmation with remaining quota (e.g. `เหลือโควต้า double รอบนี้ 1/2`)
7. Trigger `recalculate_all` (no-op if match unplayed — safe to always call)

---

## Display Changes

### `/result [player]`

Doubled picks get a `🔥x2` marker inline:

```
อาร์เจนตินา vs อียิปต์
  ทาย: 2-1 🔥x2  |  จริง: ⏳  |  —
```

Resolved:
```
  ทาย: 2-1 🔥x2  |  จริง: 2-1  |  ✅ 4 แต้ม
```
```
  ทาย: 2-1 🔥x2  |  จริง: 0-1  |  ❌ -2 แต้ม
```

### `/stand`

No change to point totals — `predictions.points` already includes doubled math via `recalculate_all`. Cosmetic addition only:

- Append 🔥 next to player name if they have any `doubled=1` prediction where `match.round` == current active round (regardless of resolved/pending) — flag persists for the whole round, not just while pending, then resets naturally once the round advances.
- Footer line added: `🔥 = ใช้ double ในรอบนี้แล้ว`

```
🏆 ตารางคะแนน World Cup 2026
(อัพเดท: 09/07/2026)

 1. Kritsana Th. 🔥      26 แต้ม
 2. saravuts_เอ          27 แต้ม
 ...

🔥 = ใช้ double ในรอบนี้แล้ว
```

Reuses the same round-scoped query as the quota check in `/double` — no new query logic.

### `/help`

Add one line describing `/double` (admin-only, usage syntax, current round's remaining quota not shown here — check via `/stand` 🔥 marker or `/result`).

---

## Testing

- `test_scoring.py`: add cases — doubled exact, doubled correct-only, doubled wrong (must be exactly -2, not 0)
- Quota enforcement: reject at cap, toggle-off refunds quota correctly
- Deadline: `/double` rejected after match deadline same as prediction parser
- `/stand` 🔥 marker: shows for round with any doubled pick (pending or resolved), absent once round changes
