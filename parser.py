from __future__ import annotations

import re
from typing import Optional

# Finds: <anything> <digits> <sep> <digits> <anything>
# Sep: colon, hyphen, en-dash U+2013
_SCORE_RE = re.compile(r'(.+?)\s*(\d+)\s*[:\-–]\s*(\d+)\s*(.+)', re.UNICODE)


def _match_team(text: str, teams: dict) -> Optional[str]:
    text = text.strip()
    if text in teams:
        return teams[text]
    text_lower = text.lower()
    for k, v in teams.items():
        if k.lower() == text_lower:
            return v
    return None


def parse_predictions(text: str, teams: dict) -> list:
    """
    Parse all score predictions from a multi-line message.
    Returns list of (home_en, home_score, away_score, away_en).
    Last prediction for a given home+away pair wins.
    """
    if text.startswith("/"):
        return []

    seen: dict = {}

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _SCORE_RE.match(line)
        if not m:
            continue
        before, h, a, after = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
        home = _match_team(before, teams)
        away = _match_team(after, teams)
        if home and away:
            seen[(home, away)] = (home, h, a, away)

    return list(seen.values())
