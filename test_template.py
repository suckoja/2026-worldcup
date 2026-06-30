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
