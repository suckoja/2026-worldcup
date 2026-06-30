#!/usr/bin/env python3
"""Cron script: push today's match template to LINE group at 6 AM ICT."""
from __future__ import annotations

import json

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
