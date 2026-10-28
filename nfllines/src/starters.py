"""
Serving-time guard on the starting QB.

For an upcoming game, nflverse's schedule home_qb_id/away_qb_id hold its
*expected* starter, and that column is not always updated when the starter
is hurt: 2026 week 7 listed Jalen Hurts for PHI while he was on IR (Tanner
McKee started), which moved PHI from ~52% to ~60%. The same happened to ATL
in week 2 and WAS in week 3.

So before serving, the listed QB is checked against that week's roster and
final injury report. If he is ruled out (IR/PUP/suspended/inactive on the
roster, or Out/Doubtful on the report), the team's most recent starter who
is available takes his place. Historical rows never hit this: there the
schedule column is the QB who actually started.
"""
from __future__ import annotations

import pandas as pd

from src.data.injury_context import OUT_ROSTER_STATUS

# INA (game-day inactive) only exists close to kickoff; when it is there it is real.
QB_OUT_ROSTER = OUT_ROSTER_STATUS | {"INA"}
QB_OUT_REPORT = {"Out", "Doubtful"}


def qb_out_reason(qb_id, team: str, season: int, week: int, rosters: dict, injuries: dict) -> str | None:
    """Why this QB will not play this week, or None if nothing says so."""
    if not isinstance(qb_id, str):
        return "no starter listed"
    st = rosters.get((season, week, team), {}).get(qb_id)
    if st in QB_OUT_ROSTER:
        return f"roster status {st}"
    rep = injuries.get((season, week, team), {}).get(qb_id)
    if rep and rep[0] in QB_OUT_REPORT:
        return f"injury report {rep[0]}"
    return None


def serving_starter(listed, team: str, season: int, week: int, qb_games: pd.DataFrame,
                    rosters: dict, injuries: dict, qb_ids: set | None = None) -> tuple:
    """(qb_id, note). note is None when the listed starter stands; otherwise
    it says why he was replaced (or why no replacement was found). `qb_ids`,
    the players listed at QB, keeps a trick-play passer from being chosen."""
    why = qb_out_reason(listed, team, season, week, rosters, injuries)
    if why is None:
        return listed, None
    roster = rosters.get((season, week, team), {})
    past = qb_games[(qb_games.team == team)
                    & ((qb_games.season < season) | ((qb_games.season == season) & (qb_games.week < week)))]
    # most recent game first, the main passer of each game first
    past = past.sort_values(["season", "week", "dropbacks", "qb_id"],
                            ascending=[False, False, False, True], kind="mergesort")
    for q in dict.fromkeys(past.qb_id):
        if q == listed or (roster and q not in roster) or (qb_ids is not None and q not in qb_ids):
            continue
        if qb_out_reason(q, team, season, week, rosters, injuries) is None:
            return q, f"listed QB out ({why}); using last available starter"
    return listed, f"listed QB out ({why}); no available replacement found, kept"
