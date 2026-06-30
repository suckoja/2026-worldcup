from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Optional

import db
import scoring
import fetcher

ICT = timezone(timedelta(hours=7))


def _is_admin(user_id: str, config: dict) -> bool:
    return user_id == config.get("ADMIN_LINE_USER_ID", "")


def _standings_text(conn: sqlite3.Connection) -> str:
    rows = db.get_standings(conn)
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
        lines.append(f"{rank:2}. {row['line_display_name']:<22} {pts} แต้ม{star}")
    return "\n".join(lines)


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
        actual = (f"{row['home_score']}-{row['away_score']}"
                  if row["home_score"] is not None else "⏳")
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


def _result_date_text(conn: sqlite3.Connection, date_str: str) -> str:
    rows = db.get_today_predictions(conn, date_str)
    if not rows:
        return f"ไม่มีการแข่งขันวันที่ {date_str}"

    d_display = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d/%m/%Y")
    lines = [f"📅 ผลการทาย {d_display}", ""]
    current_match: Optional[tuple] = None

    for row in rows:
        match_key = (row["home_team_en"], row["away_team_en"])
        if match_key != current_match:
            current_match = match_key
            home_th = row["home_team_th"] or row["home_team_en"]
            away_th = row["away_team_th"] or row["away_team_en"]
            actual = (f"{row['home_score']}-{row['away_score']}"
                      if row["home_score"] is not None else "⏳ รอผล")
            lines.append(f"⚽ {home_th} vs {away_th}")
            lines.append(f"  จริง: {actual}")

        if row["line_display_name"]:
            pred = f"{row['home_pred']}-{row['away_pred']}"
            pts = f" ({row['points']} แต้ม)" if row["points"] is not None else ""
            lines.append(f"  {row['line_display_name']:<22} {pred}{pts}")

    return "\n".join(lines)


def _result_today_text(conn: sqlite3.Connection) -> str:
    return _result_date_text(conn, db.today_ict())


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
        if arg.lower() == "me":
            if not display_name:
                return "❌ ระบุชื่อไม่ได้ ลองพิมพ์ /result [ชื่อ] แทน"
            name, candidates = db.resolve_player(display_name, players)
            if name:
                player_id = db.get_player_id(conn, name)
                return _result_player_text(conn, player_id, name)
            all_names = "\n".join(f"- {p['line_display_name']}" for p in players)
            return f"❌ ไม่พบชื่อ '{display_name}' ในระบบ\nผู้เล่นทั้งหมด:\n{all_names}"
        # YYYY-MM-DD date lookup
        if re.match(r'^\d{4}-\d{2}-\d{2}$', arg):
            try:
                datetime.strptime(arg, "%Y-%m-%d")
            except ValueError:
                return f"❌ วันที่ไม่ถูกต้อง '{arg}'"
            return _result_date_text(conn, arg)
        name, candidates = db.resolve_player(arg, players)
        if name:
            player_id = db.get_player_id(conn, name)
            if not player_id:
                db.upsert_player(conn, name)
                player_id = db.get_player_id(conn, name)
            return _result_player_text(conn, player_id, name)
        if candidates:
            return ("❌ ชื่อตรงกับหลายคน:\n"
                    + "\n".join(f"- {c}" for c in candidates)
                    + "\nพิมพ์ชื่อให้ชัดขึ้น")
        all_names = "\n".join(f"- {p['line_display_name']}" for p in players)
        return f"❌ ไม่พบผู้เล่น '{arg}'\nผู้เล่นทั้งหมด:\n{all_names}"

    if cmd == "/help":
        return _help_text()

    if cmd == "/sync":
        if not _is_admin(user_id, config):
            return None
        try:
            updated, needs_manual = fetcher.sync_results(conn, config["FOOTBALL_DATA_API_KEY"])
            if updated:
                scoring.recalculate_all(conn, rules)
            lines = []
            if updated:
                lines.append(f"🔄 อัพเดท {len(updated)} นัด:")
                lines.extend(f"✅ {r}" for r in updated)
                lines.append(f"\n📊 คำนวณคะแนนเสร็จแล้ว")
            if needs_manual:
                lines.append(f"\n⚠️ ต้องใส่คะแนน 90 นาที ด้วย /setscore:")
                lines.extend(f"  • {m}" for m in needs_manual)
            if not lines:
                return "ไม่มีผลใหม่"
            lines.append("\nพิมพ์ /stand เพื่อดูตาราง")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ ดึงข้อมูลไม่ได้ ลองใหม่ภายหลัง ({e})"

    if cmd == "/seed":
        if not _is_admin(user_id, config):
            return None
        # /seed [player] [YYYY-MM-DD] [home] [H-A] [away]
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

        score_m = re.match(r'(\d+)[:\-–](\d+)', score_arg)
        if not score_m:
            return f"❌ สกอร์ไม่ถูกต้อง '{score_arg}' ใช้รูปแบบ H-A เช่น 0-2"

        home_pred, away_pred = int(score_m.group(1)), int(score_m.group(2))

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

    if cmd == "/setscore":
        if not _is_admin(user_id, config):
            return None
        # /setscore [home] [H-A] [away]
        if len(parts) < 4:
            return "❌ รูปแบบ: /setscore [ทีมเหย้า] [H-A] [ทีมเยือน] เช่น /setscore Brazil 1-1 France"
        score_arg = parts[-2]
        home_arg = " ".join(parts[1:-2]).strip('"')
        away_arg = parts[-1].strip('"')

        score_m = re.match(r'(\d+)[:\-–](\d+)', score_arg)
        if not score_m:
            return f"❌ สกอร์ไม่ถูกต้อง '{score_arg}' ใช้รูปแบบ H-A เช่น 1-1"

        home_score, away_score = int(score_m.group(1)), int(score_m.group(2))

        home_en = teams.get(home_arg) or (home_arg if home_arg in teams.values() else None)
        away_en = teams.get(away_arg) or (away_arg if away_arg in teams.values() else None)
        if not home_en:
            return f"❌ ไม่พบทีม '{home_arg}'"
        if not away_en:
            return f"❌ ไม่พบทีม '{away_arg}'"

        match_row = db.get_match_by_teams(conn, home_en, away_en)
        if not match_row:
            return f"❌ ไม่พบนัด {home_en} vs {away_en}"

        conn.execute(
            "UPDATE matches SET home_score = ?, away_score = ? WHERE id = ?",
            (home_score, away_score, match_row["id"])
        )
        conn.commit()
        scoring.recalculate_all(conn, rules)

        home_th = match_row["home_team_th"] or home_en
        away_th = match_row["away_team_th"] or away_en
        return (
            f"✅ บันทึกผล 90 นาทีแล้ว\n"
            f"{home_th} vs {away_th}: {home_score}-{away_score}\n"
            f"📊 คำนวณคะแนนเสร็จแล้ว — พิมพ์ /stand เพื่อดูตาราง"
        )

    if cmd == "/setgroup":
        if not _is_admin(user_id, config):
            return None
        if not group_id:
            return "❌ ใช้คำสั่งนี้ในกลุ่มเท่านั้น"
        return "__SETGROUP__"

    return None
