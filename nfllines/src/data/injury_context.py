"""
Point-in-time lookups the injury tracker reads: the final weekly injury
report, weekly rosters, per-game snap shares, and a per-player quality
signal (contract APY as % of cap, draft capital). Built once from the cached
nflverse tables and handed to the engine as `context`.

Timing facts (checked on the raw data, see README):
* nflverse's injuries table has ONE row per player-week — the final report,
  date-stamped the day before the game in 95% of rows. That is the Friday
  report the model is allowed to see.
* Weekly rosters carry the status for that week (ACT / RES = injured
  reserve / PUP / SUS ...). A player on IR is not on the injury report; his
  roster status is what says he is out.
* Contracts: Over The Cap via nflverse. A player's contract for season S is
  the latest one signed in or before S. An in-season extension is therefore
  visible for the weeks before it was signed — a small, documented
  labour-market look-ahead; it is not betting-market data.
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd

from src.data import nflverse as nv
from src.data.team_games import TEAM_RENAME

# P(plays | final report status, practice) measured on 2015-2023
# (experiments in README "Stage 4"). "played" = took at least one snap.
P_PLAY = {
    ("Out", "*"): 0.0,
    ("Doubtful", "*"): 0.01,
    ("Questionable", "DNP"): 0.41,
    ("Questionable", "Limited"): 0.69,
    ("Questionable", "Full"): 0.82,
    ("Questionable", "*"): 0.67,
    ("Probable", "*"): 0.95,
    ("NotListed", "DNP"): 0.74,
    ("NotListed", "Limited"): 0.935,
    ("NotListed", "Full"): 0.95,
    ("NotListed", "*"): 0.93,
}
P_PLAY_HEALTHY = 0.95          # not on the report at all
OUT_ROSTER_STATUS = {"RES", "PUP", "SUS", "NWT", "RSN", "RSR", "EXE", "RET", "CUT", "UFA", "RFA"}

POSITION_GROUP = {
    "RB": "RB", "HB": "RB", "FB": "RB",
    "WR": "WR", "TE": "TE",
    "T": "OL", "G": "OL", "C": "OL", "OL": "OL", "OT": "OL", "LT": "OL", "RT": "OL", "LG": "OL", "RG": "OL",
    "C/G": "OL", "G/T": "OL", "G/C": "OL",
    "DE": "DL", "DT": "DL", "NT": "DL", "DL": "DL", "IDL": "DL", "ED": "DL", "EDGE": "DL",
    "LB": "LB", "OLB": "LB", "ILB": "LB", "MLB": "LB",
    "CB": "DB", "S": "DB", "FS": "DB", "SS": "DB", "DB": "DB",
}
GROUPS = ["RB", "WR", "TE", "OL", "DL", "LB", "DB"]


def practice_code(s) -> str:
    if not isinstance(s, str):
        return "*"
    if s.startswith("Full"):
        return "Full"
    if s.startswith("Limited"):
        return "Limited"
    if s.startswith("Did Not"):
        return "DNP"
    return "*"


def p_play(status, practice) -> float:
    status = status if isinstance(status, str) and status in {"Out", "Doubtful", "Questionable", "Probable"} else "NotListed"
    return P_PLAY.get((status, practice), P_PLAY.get((status, "*"), P_PLAY_HEALTHY))


def draft_value(pick) -> float:
    if pick is None or (isinstance(pick, float) and np.isnan(pick)):
        return 0.0
    return float(np.exp(-(float(pick) - 1.0) / 50.0))


def build_context(seasons, games: pd.DataFrame) -> dict:
    seasons = list(seasons)
    players = nv.load_players()
    pfr2gsis = players.dropna(subset=["pfr_id"]).drop_duplicates("pfr_id").set_index("pfr_id").gsis_id

    # positions
    pos = {}
    for r in players[["gsis_id", "position"]].itertuples(index=False):
        if isinstance(r.position, str):
            pos[r.gsis_id] = POSITION_GROUP.get(r.position)

    # injuries: (season, week, team) -> {gsis: (status, practice)}
    inj = nv.cached_seasons("injuries", nv.load_injuries, seasons)
    inj["team"] = inj.team.replace(TEAM_RENAME)
    injuries = defaultdict(dict)
    for r in inj.itertuples(index=False):
        if pd.isna(r.week) or not isinstance(r.gsis_id, str):
            continue
        injuries[(int(r.season), int(r.week), r.team)][r.gsis_id] = (
            r.report_status if isinstance(r.report_status, str) else "NotListed",
            practice_code(r.practice_status))
        if r.gsis_id not in pos and isinstance(r.position, str):
            pos[r.gsis_id] = POSITION_GROUP.get(r.position)

    # rosters: (season, week, team) -> {gsis: status}
    ros = nv.cached_seasons("rosters_weekly", nv.load_rosters_weekly, seasons)
    ros = ros[ros.season.isin(seasons) & ros.game_type.isin(nv.GAME_TYPES)]
    ros["team"] = ros.team.replace(TEAM_RENAME)
    rosters = defaultdict(dict)
    for r in ros[["season", "week", "team", "gsis_id", "status", "position"]].itertuples(index=False):
        if not isinstance(r.gsis_id, str):
            continue
        rosters[(int(r.season), int(r.week), r.team)][r.gsis_id] = r.status
        if r.gsis_id not in pos and isinstance(r.position, str):
            pos[r.gsis_id] = POSITION_GROUP.get(r.position)

    # snaps: (game_id, team) -> {gsis: max(off_pct, def_pct)}
    sn = nv.cached_seasons("snaps", nv.load_snap_counts, seasons)
    sn = sn[sn.season.isin(seasons)].copy()
    sn["gsis_id"] = sn.pfr_player_id.map(pfr2gsis)
    sn["team"] = sn.team.replace(TEAM_RENAME)
    sn["pct"] = np.maximum(sn.offense_pct.fillna(0), sn.defense_pct.fillna(0))
    snaps = defaultdict(dict)
    for r in sn.dropna(subset=["gsis_id"])[["game_id", "team", "gsis_id", "pct"]].itertuples(index=False):
        snaps[(r.game_id, r.team)][r.gsis_id] = float(r.pct)

    # contracts: gsis -> sorted [(year_signed, apy_cap_pct)]
    c = nv.load_contracts().dropna(subset=["gsis_id"])
    c = c[(c.year_signed > 0) & c.apy_cap_pct.notna()]
    contracts = defaultdict(list)
    for r in c[["gsis_id", "year_signed", "apy_cap_pct"]].sort_values("year_signed").itertuples(index=False):
        contracts[r.gsis_id].append((int(r.year_signed), float(r.apy_cap_pct)))
    picks = players.dropna(subset=["draft_pick"]).set_index("gsis_id").draft_pick.to_dict()

    def quality(gsis, season) -> tuple:
        apy = 0.0
        for ys, a in contracts.get(gsis, []):
            if ys <= season:
                apy = a
        return apy, draft_value(picks.get(gsis))

    return {"injuries": injuries, "rosters": rosters, "snaps": snaps, "positions": pos,
            "quality": quality}
