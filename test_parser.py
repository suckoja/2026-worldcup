import json
from parser import parse_predictions

TEAMS = json.load(open("teams.json", encoding="utf-8"))


def test_colon_separator():
    assert parse_predictions("บราซิล 2:1 ญี่ปุ่น", TEAMS) == [("Brazil", 2, 1, "Japan")]


def test_hyphen_separator():
    assert parse_predictions("บราซิล 2-1 ญี่ปุ่น", TEAMS) == [("Brazil", 2, 1, "Japan")]


def test_endash_separator():
    assert parse_predictions("บราซิล 2–1 ญี่ปุ่น", TEAMS) == [("Brazil", 2, 1, "Japan")]


def test_no_space_between_score_and_team():
    assert parse_predictions("เยอรมนี 2–0ปารากวัย", TEAMS) == [("Germany", 2, 0, "Paraguay")]


def test_spaces_around_separator():
    assert parse_predictions("เนเธอร์แลนด์ 1 – 0โมร็อกโก", TEAMS) == [("Netherlands", 1, 0, "Morocco")]


def test_english_team_names():
    assert parse_predictions("Brazil 2:1 Japan", TEAMS) == [("Brazil", 2, 1, "Japan")]


def test_multi_line_three_matches():
    text = "บราซิล 2:1 ญี่ปุ่น\nเยอรมัน 2:0 ปารากวัย\nเนเธอร์แลนด์ 1:1 โมร็อกโก"
    result = parse_predictions(text, TEAMS)
    assert len(result) == 3
    assert ("Brazil", 2, 1, "Japan") in result
    assert ("Germany", 2, 0, "Paraguay") in result
    assert ("Netherlands", 1, 1, "Morocco") in result


def test_multi_line_last_wins():
    text = "บราซิล 2:1 ญี่ปุ่น\nบราซิล 1:0 ญี่ปุ่น"
    result = parse_predictions(text, TEAMS)
    assert result == [("Brazil", 1, 0, "Japan")]


def test_invalid_format_no_separator():
    assert parse_predictions("บราซิล 2 ญี่ปุ่น", TEAMS) == []


def test_slash_separator_rejected():
    assert parse_predictions("บราซิล 2/1 ญี่ปุ่น", TEAMS) == []


def test_non_prediction_text_ignored():
    assert parse_predictions("ขอตารางคะแนนด้วยนะ", TEAMS) == []


def test_command_ignored():
    assert parse_predictions("/stand", TEAMS) == []


def test_unknown_team_ignored():
    assert parse_predictions("ดาวอังคาร 2:1 ดาวพฤหัส", TEAMS) == []


def test_draw():
    assert parse_predictions("บราซิล 0:0 ญี่ปุ่น", TEAMS) == [("Brazil", 0, 0, "Japan")]


def test_real_chat_moroukko_variant():
    # โมรอคโค is alternate spelling used in chat
    result = parse_predictions("เนเธอแลนด์ 1:1 โมรอคโค", TEAMS)
    assert result == [("Netherlands", 1, 1, "Morocco")]
