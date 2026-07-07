from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Optional

import db
import scoring
import fetcher
import template as tmpl

ICT = timezone(timedelta(hours=7))


def _is_admin(user_id: str, config: dict) -> bool:
    return user_id == config.get("ADMIN_LINE_USER_ID", "")


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
            double_marker = " 🔥x2" if row["doubled"] else ""
            pts = f" ({row['points']} แต้ม)" if row["points"] is not None else ""
            lines.append(f"  {row['line_display_name']:<22} {pred}{double_marker}{pts}")

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
        "/double [ชื่อ] [ทีมเหย้า] [ทีมเยือน] — เปิด/ปิด double (admin, x2 ถ้าถูก, -2 ถ้าผิด)\n"
        "/seed [ชื่อ] [YYYY-MM-DD] [ทีมเหย้า] [H-A] [ทีมเยือน] — บันทึกย้อนหลัง (admin)\n"
        "/setgroup — บันทึก group ID สำหรับส่ง template (admin, ใช้ในกลุ่ม)\n"
        "/template [YYYY-MM-DD] — ดู template (admin, default: วันนี้)\n"
        "/add_fixture [match_date] [kickoff_utc] [deadline_ict] [ทีมเหย้า] [ทีมเยือน] [round] — เพิ่มนัดใหม่ (admin)\n"
        "/remove_fixture [ทีมเหย้า] [ทีมเยือน] [round] — ลบนัด (admin)\n"
        "/fixtures [round] — ดูนัดที่เหลือ\n"
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

    if cmd == "/add_fixture":
        if not _is_admin(user_id, config):
            return None
        # /add_fixture [match_date_ict] [kickoff_utc] [deadline_ict] [home_th] [away_th] [round]
        if len(parts) < 6 or len(parts) > 7:
            return ("❌ รูปแบบ: /add_fixture [YYYY-MM-DD] [kickoff_utc] [deadline_ict] "
                    "[ทีมเหย้า] [ทีมเยือน] [round]\nตัวอย่าง: /add_fixture 2026-07-07 "
                    "2026-07-07T00:00:00Z 2026-07-06T08:00:00 อาร์เจนตินา ออสเตรเลีย 16")
        match_date, kickoff_utc, deadline_ict, home_th, away_th = parts[1:6]
        round_arg = parts[6] if len(parts) == 7 else "16"

        if not re.match(r'^\d{4}-\d{2}-\d{2}$', match_date):
            return f"❌ match_date ไม่ถูกต้อง '{match_date}' รูปแบบ YYYY-MM-DD"
        if not re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$', kickoff_utc):
            return f"❌ kickoff_utc ไม่ถูกต้อง '{kickoff_utc}' รูปแบบ YYYY-MM-DDTHH:MM:SSZ"
        if not re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$', deadline_ict):
            return f"❌ deadline_ict ไม่ถูกต้อง '{deadline_ict}' รูปแบบ YYYY-MM-DDTHH:MM:SS"

        home_en = teams.get(home_th)
        away_en = teams.get(away_th)
        if not home_en:
            return f"❌ ไม่พบทีม '{home_th}'"
        if not away_en:
            return f"❌ ไม่พบทีม '{away_th}'"

        dup = conn.execute(
            "SELECT id FROM matches WHERE home_team_en = ? AND away_team_en = ? AND round = ?",
            (home_en, away_en, round_arg)
        ).fetchone()
        if dup:
            return f"❌ นัด {home_en} vs {away_en} (round {round_arg}) มีอยู่แล้ว"

        conn.execute("""
            INSERT INTO matches
            (match_date_ict, kickoff_utc, deadline_ict, home_team_en, away_team_en,
             home_team_th, away_team_th, round)
            VALUES (?,?,?,?,?,?,?,?)
        """, (match_date, kickoff_utc, deadline_ict, home_en, away_en, home_th, away_th, round_arg))
        conn.commit()

        return (
            f"✅ เพิ่มนัดแล้ว\n"
            f"{home_th} vs {away_th} (round {round_arg})\n"
            f"วันที่: {match_date}  kickoff: {kickoff_utc}"
        )

    if cmd == "/remove_fixture":
        if not _is_admin(user_id, config):
            return None
        # /remove_fixture [home_th] [away_th] [round]
        if len(parts) != 4:
            return "❌ รูปแบบ: /remove_fixture [ทีมเหย้า] [ทีมเยือน] [round]"
        home_th, away_th, round_arg = parts[1], parts[2], parts[3]

        home_en = teams.get(home_th)
        away_en = teams.get(away_th)
        if not home_en:
            return f"❌ ไม่พบทีม '{home_th}'"
        if not away_en:
            return f"❌ ไม่พบทีม '{away_th}'"

        match_row = conn.execute(
            "SELECT id FROM matches WHERE home_team_en = ? AND away_team_en = ? AND round = ?",
            (home_en, away_en, round_arg)
        ).fetchone()
        if not match_row:
            return f"❌ ไม่พบนัด {home_en} vs {away_en} (round {round_arg})"

        pred_count = conn.execute(
            "SELECT COUNT(*) AS n FROM predictions WHERE match_id = ?", (match_row["id"],)
        ).fetchone()["n"]
        if pred_count > 0:
            return f"❌ มีคนทายนัดนี้แล้ว ({pred_count} คน) ลบไม่ได้"

        conn.execute("DELETE FROM matches WHERE id = ?", (match_row["id"],))
        conn.commit()
        return f"✅ ลบนัด {home_en} vs {away_en} (round {round_arg}) แล้ว"

    if cmd == "/fixtures":
        round_arg = parts[1] if len(parts) > 1 else None
        if round_arg:
            rows = conn.execute(
                "SELECT home_team_th, away_team_th, home_team_en, away_team_en, "
                "match_date_ict FROM matches WHERE home_score IS NULL AND round = ? "
                "ORDER BY kickoff_utc",
                (round_arg,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT home_team_th, away_team_th, home_team_en, away_team_en, "
                "match_date_ict, round FROM matches WHERE home_score IS NULL "
                "ORDER BY kickoff_utc"
            ).fetchall()
        if not rows:
            return "ไม่มีนัดที่เหลือ"

        if round_arg:
            lines = ["นัดที่เหลือ:"]
            for r in rows:
                home = r["home_team_th"] or r["home_team_en"]
                away = r["away_team_th"] or r["away_team_en"]
                lines.append(f"{home} vs {away} ({r['match_date_ict']})")
            return "\n".join(lines)

        round_labels = {
            "32": "รอบ 32 ทีมสุดท้าย",
            "16": "รอบ 16 ทีมสุดท้าย",
            "8": "รอบ 8 ทีมสุดท้าย",
            "4": "รอบรองชนะเลิศ",
            "2": "รอบชิงชนะเลิศ",
        }

        def round_sort_key(round_val):
            try:
                return -int(round_val)
            except ValueError:
                return 0

        rounds_seen = sorted({r["round"] for r in rows}, key=round_sort_key)
        rows_by_round = {rnd: [] for rnd in rounds_seen}
        for r in rows:
            rows_by_round[r["round"]].append(r)

        blocks = []
        for rnd in rounds_seen:
            label = round_labels.get(rnd, f"รอบ {rnd}")
            block_lines = [f"-- {label} --"]
            for r in rows_by_round[rnd]:
                home = r["home_team_th"] or r["home_team_en"]
                away = r["away_team_th"] or r["away_team_en"]
                block_lines.append(f"{home} vs {away} ({r['match_date_ict']})")
            blocks.append("\n".join(block_lines))
        return "\n\n".join(blocks)

    if cmd == "/setgroup":
        if not _is_admin(user_id, config):
            return None
        if not group_id:
            return "❌ ใช้คำสั่งนี้ในกลุ่มเท่านั้น"
        return "__SETGROUP__"

    if cmd == "/template":
        if not _is_admin(user_id, config):
            return None
        date_arg = parts[1] if len(parts) > 1 and re.match(r'\d{4}-\d{2}-\d{2}', parts[1]) else db.today_ict()
        rows = conn.execute(
            "SELECT home_team_th, away_team_th, home_team_en, away_team_en, kickoff_utc "
            "FROM matches WHERE match_date_ict = ? ORDER BY kickoff_utc",
            (date_arg,)
        ).fetchall()
        if not rows:
            return f"ไม่มีแมตช์วันที่ {date_arg}"
        return f"__SENDTEMPLATE__:{date_arg}"

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

        kickoff = datetime.fromisoformat(
            match_row["kickoff_utc"].replace("Z", "+00:00")
        )
        if datetime.now(timezone.utc) > kickoff:
            return "❌ นัดเริ่มแล้ว double ไม่ได้"

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

    return None
