"""
When is a game's prediction allowed to be logged?
=================================================
The model was trained on FINAL injury reports (the last report before each
game). A prediction logged from a mid-week practice report is a train/serve
skew: week 2 of 2026 was predicted from a Thursday snapshot that had 6 game
statuses where the final report had 105. So a game is logged only when:

1. It has not kicked off.
2. Its final report deadline has passed: 4 pm ET on the last practice day,
   which is the day before a Thursday game and two days before any other
   (Friday for Sunday, Saturday for Monday, Thursday for Saturday).
3. The data shows it: both teams filed a report for the week, and at least
   one of them carries a game status (Out / Doubtful / Questionable). In the
   final reports of 2019-2025, 97.7% of team-weeks carry one; in a mid-week
   snapshot only the Thursday teams do.
4. Every earlier game of the season has a result and play-by-play, so the
   ratings the prediction stands on are complete (a Monday night game missing
   on Tuesday blocks the next week until nflverse has it).

Practical schedule: run Wednesday evening (logs the Thursday game) and
Saturday evening (logs Sunday and Monday). Late-season Saturday games are
ready from Thursday evening.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

ET = ZoneInfo("America/New_York")
REPORT_HOUR_ET = 16


def kickoff_et(g) -> datetime:
    return datetime.fromisoformat(f"{pd.Timestamp(g['gameday']).date()} {g['gametime']}").replace(tzinfo=ET)


def report_due_et(g) -> datetime:
    ko = kickoff_et(g)
    days = 1 if ko.weekday() == 3 else 2          # Thursday game: Wednesday report
    d = (ko - timedelta(days=days)).date()
    return datetime(d.year, d.month, d.day, REPORT_HOUR_ET, tzinfo=ET)


def injury_report_state(injuries: dict, season: int, week: int, team: str) -> tuple[bool, bool]:
    """(filed, has_game_status) for a team-week in the injury context."""
    rep = injuries.get((season, week, team))
    if not rep:
        return False, False
    return True, any(st != "NotListed" for st, _ in rep.values())


def season_complete_before(games: pd.DataFrame, team_games: pd.DataFrame, season: int, week: int,
                           now: datetime) -> list:
    """Earlier-week games of `season` that have kicked off but lack a score or
    play-by-play. Empty list = the ratings are complete."""
    earlier = games[(games.season == season) & (games.week < week)]
    missing = []
    have_pbp = set(team_games.game_id)
    for _, g in earlier.iterrows():
        if kickoff_et(g) > now:
            continue
        if pd.isna(g["home_score"]):
            missing.append(f"{g['game_id']} (no score)")
        elif g["game_id"] not in have_pbp:
            missing.append(f"{g['game_id']} (no play-by-play)")
    return missing


def game_readiness(g, injuries: dict, now: datetime) -> tuple[bool, str]:
    ko, due = kickoff_et(g), report_due_et(g)
    if now >= ko:
        return False, "kicked off"
    if now < due:
        return False, f"final injury report due {due:%a %H:%M} ET"
    season, week = int(g["season"]), int(g["week"])
    h = injury_report_state(injuries, season, week, g["home_team"])
    a = injury_report_state(injuries, season, week, g["away_team"])
    if not (h[0] and a[0]):
        who = [t for t, st in ((g["home_team"], h), (g["away_team"], a)) if not st[0]]
        return False, f"no injury report yet in nflverse for {', '.join(who)}"
    if not (h[1] or a[1]):
        return False, "injury report has no game statuses yet (looks mid-week); rerun later"
    return True, "ready"
