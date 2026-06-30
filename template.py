from __future__ import annotations

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
