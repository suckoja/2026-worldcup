# Server

Production runs on EC2, `ec2-user@ip-172-31-33-175` (ap-southeast-1), managed by
systemd as `worldcup-bot`. Flask app listens on `127.0.0.1:8000` / `0.0.0.0:8000`.

## Deploy (code change)

```
ssh ec2-user@<host>
cd ~/worldcup
git pull
sudo systemctl restart worldcup-bot
sudo systemctl status worldcup-bot
```

`worldcup.db` is gitignored — `git pull` never touches it. Schema/data changes
(new columns, indexes, seed rows) need a separate manual step, see below.

## Deploy (schema or seed change)

No `sqlite3` CLI on the box — use `python3 -c "..."` with the stdlib `sqlite3`
module, or run project scripts through the venv.

Re-seeding is safe to rerun — `matches` has a
`UNIQUE(home_team_en, away_team_en, round)` index, so `INSERT OR IGNORE`
won't duplicate rows:

```
cd ~/worldcup
venv/bin/python seeds/init_db.py
```

For one-off schema tweaks (e.g. adding an index that predates a given deploy):

```
python3 -c "
import sqlite3
c = sqlite3.connect('worldcup.db')
c.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_matches_unique ON matches(home_team_en, away_team_en, round)')
c.commit()
"
```

Before any dedup/delete on `matches`, check nothing in `predictions` points at
the rows you're about to remove:

```
python3 -c "
import sqlite3
c = sqlite3.connect('worldcup.db')
print(c.execute('SELECT home_team_en, away_team_en, round, COUNT(*) c FROM matches GROUP BY home_team_en, away_team_en, round HAVING c>1').fetchall())
"
```

## Restart / logs

```
sudo systemctl restart worldcup-bot
sudo systemctl status worldcup-bot
journalctl -u worldcup-bot -n 50 --no-pager
journalctl -u worldcup-bot -f          # tail live
```

## Smoke test after any deploy

In LINE, as admin:
- `/help` — confirms new commands are live
- `/fixtures 16` (or whichever round changed) — confirms DB data matches code

## systemd unit

`/etc/systemd/system/worldcup-bot.service`:

```ini
[Unit]
Description=World Cup 2026 LINE Bot
After=network.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/home/ec2-user/worldcup
ExecStart=/home/ec2-user/worldcup/venv/bin/python bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

`Restart=always` — crashes auto-restart after 5s, no manual intervention needed
for transient failures. Dev-server warning in Flask logs is expected (LINE
webhook traffic is low-volume enough that `flask run`'s dev server is fine
here; revisit gunicorn/waitress if that stops being true).
