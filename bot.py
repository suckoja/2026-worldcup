from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone, timedelta

from flask import Flask, request, abort, render_template
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    ReplyMessageRequest, TextMessage, PushMessageRequest
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent, UnsendEvent

import db
import commands
import parser as pred_parser

app = Flask(__name__, template_folder="dashboard/templates")

ICT = timezone(timedelta(hours=7))


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


def _line_api(config: dict) -> MessagingApi:
    cfg = Configuration(access_token=config["LINE_CHANNEL_ACCESS_TOKEN"])
    return MessagingApi(ApiClient(cfg))


def reply(reply_token: str, text: str, config: dict):
    api = _line_api(config)
    api.reply_message(ReplyMessageRequest(
        reply_token=reply_token,
        messages=[TextMessage(text=text)]
    ))


def push(user_id: str, text: str, config: dict):
    api = _line_api(config)
    api.push_message(PushMessageRequest(
        to=user_id,
        messages=[TextMessage(text=text)]
    ))


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

    # Sync all known players to DB
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

            # Fetch display name once for both commands and predictions
            display_name = None
            group_id = source.get("groupId")
            if group_id and user_id:
                try:
                    api = _line_api(config)
                    profile = api.get_group_member_profile(group_id, user_id)
                    display_name = profile.display_name
                except Exception:
                    pass

            if text.startswith("/"):
                response = commands.handle_command(
                    text, user_id, conn, config, players, rules, teams,
                    display_name=display_name,
                )
                if response and reply_token:
                    reply(reply_token, response, config)
            else:
                predictions = pred_parser.parse_predictions(text, teams)
                if not predictions:
                    continue

                submitted_at = datetime.now(ICT).strftime("%Y-%m-%dT%H:%M:%S")

                if not display_name:
                    continue

                resolved, _ = db.resolve_player(display_name, players)
                if not resolved:
                    # Notify admin
                    admin_id = config.get("ADMIN_LINE_USER_ID")
                    if admin_id:
                        try:
                            push(admin_id,
                                 f"⚠️ ผู้เล่นใหม่: {display_name}\nกรุณาเพิ่มใน players.json",
                                 config)
                        except Exception:
                            pass
                    continue

                db.upsert_player(conn, resolved)
                player_id = db.get_player_id(conn, resolved)

                for (home_en, home_pred, away_pred, away_en) in predictions:
                    match_row = db.get_match_by_teams(conn, home_en, away_en)
                    if not match_row:
                        continue

                    deadline = datetime.fromisoformat(
                        match_row["deadline_ict"].replace("Z", "")
                    ).replace(tzinfo=ICT)
                    now = datetime.now(ICT)

                    if now > deadline:
                        if reply_token:
                            home_th = match_row["home_team_th"] or home_en
                            away_th = match_row["away_team_th"] or away_en
                            reply(reply_token,
                                  f"❌ หมดเวลาทาย {home_th} vs {away_th} แล้ว",
                                  config)
                        continue

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


@app.route("/dashboard")
def dashboard():
    config = load_config()
    conn = get_conn(config)
    players = load_players()

    standings = db.get_standings(conn)
    matches = conn.execute(
        "SELECT * FROM matches ORDER BY kickoff_utc"
    ).fetchall()
    today = db.today_ict()
    today_rows = db.get_today_predictions(conn, today)

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
