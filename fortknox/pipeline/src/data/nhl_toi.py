"""
Time on ice by strength, from a shift chart.
============================================

Rebuilds who was on the ice every second of a game, then counts each player's
and each team's seconds at 5v5, on the power play, on the penalty kill and in
all situations. Rates per 60 minutes need the right denominator: a team's
5v5 xGF/60 is its 5v5 xG over its 5v5 minutes, not over the whole game.

A second s of a period belongs to a shift that runs (start, end], the same
convention nhl_events._Shifts uses for events, so the shots counted against a
state and the minutes spent in it line up.
"""

import numpy as np

STATES = ("all", "5v5", "pp", "pk")


def _mmss(t):
    m, s = t.split(":")
    return int(m) * 60 + int(s)


def game_toi(pbp, shifts_doc):
    """Return (players, teams): {id: {state: seconds}} for each.

    Empty dicts when the game has no shift chart.
    """
    goalies = {r["playerId"] for r in pbp.get("rosterSpots", []) if r.get("positionCode") == "G"}
    home_id, away_id = pbp["homeTeam"]["id"], pbp["awayTeam"]["id"]
    shifts = []
    for s in (shifts_doc or {}).get("data", []):
        if s.get("typeCode") != 517 or not s.get("startTime") or not s.get("endTime"):
            continue
        t0, t1 = _mmss(s["startTime"]), _mmss(s["endTime"])
        if t1 > t0 and s["teamId"] in (home_id, away_id):
            shifts.append((s["period"], t0, t1, s["playerId"], s["teamId"]))
    if not shifts:
        return {}, {}

    players, teams = {}, {home_id: dict.fromkeys(STATES, 0), away_id: dict.fromkeys(STATES, 0)}
    for p in sorted({s[0] for s in shifts}):
        ps = [s for s in shifts if s[0] == p]
        n = max(s[2] for s in ps)
        sk = {home_id: np.zeros(n + 2, int), away_id: np.zeros(n + 2, int)}
        gk = {home_id: np.zeros(n + 2, int), away_id: np.zeros(n + 2, int)}
        for _, t0, t1, pid, team in ps:
            arr = gk[team] if pid in goalies else sk[team]
            arr[t0 + 1] += 1      # seconds t0+1 .. t1 inclusive
            arr[t1 + 1] -= 1
        for d in (sk, gk):
            for k in d:
                d[k] = np.cumsum(d[k])   # index i is second i, for i in 1..n
        sec = slice(1, n + 1)
        state = {}
        for team, opp in ((home_id, away_id), (away_id, home_id)):
            s_me, s_op = sk[team][sec], sk[opp][sec]
            g_me, g_op = gk[team][sec] > 0, gk[opp][sec] > 0
            both_g = g_me & g_op
            st = {"all": np.ones(n, bool),
                  "5v5": both_g & (s_me == 5) & (s_op == 5),
                  "pp": both_g & (s_me > s_op) & (s_op >= 3),
                  "pk": both_g & (s_me < s_op) & (s_me >= 3)}
            state[team] = st
            for k, v in st.items():
                teams[team][k] += int(v.sum())
        for _, t0, t1, pid, team in ps:
            rec = players.setdefault(pid, dict.fromkeys(STATES, 0))
            for k, v in state[team].items():
                rec[k] += int(v[t0:t1].sum())   # seconds t0+1..t1 are v[t0..t1-1]
    return players, teams
