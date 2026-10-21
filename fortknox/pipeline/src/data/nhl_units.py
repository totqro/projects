"""
Who was on the ice together at 5v5, from a shift chart.
=======================================================

The lines, pairs and with-or-without-you (WOWY) tables need time on ice for
groups of players, not just for each player. This walks a game's shifts
period by period, splits each period wherever someone steps on or off, and
returns the stretches spent at 5v5 with each team's five skaters.

Same conventions as nhl_toi.game_toi: a shift covers seconds (start, end],
and 5v5 means both goalies in net and five skaters a side, so the minutes
here add up to the 5v5 minutes there.
"""


def _mmss(t):
    m, s = t.split(":")
    return int(m) * 60 + int(s)


def game_units(pbp, shifts_doc):
    """[(team_id, (skater ids, sorted), seconds)] for every 5v5 stretch.

    Empty when the game has no shift chart.
    """
    goalies = {r["playerId"] for r in pbp.get("rosterSpots", []) if r.get("positionCode") == "G"}
    teams = (pbp["homeTeam"]["id"], pbp["awayTeam"]["id"])
    by_period = {}
    for s in (shifts_doc or {}).get("data", []):
        if s.get("typeCode") != 517 or not s.get("startTime") or not s.get("endTime"):
            continue
        t0, t1 = _mmss(s["startTime"]), _mmss(s["endTime"])
        if t1 > t0 and s["teamId"] in teams:
            by_period.setdefault(s["period"], []).append((t0, t1, s["playerId"], s["teamId"]))

    out = []
    for shifts in by_period.values():
        cuts = sorted({t for t0, t1, *_ in shifts for t in (t0, t1)})
        for a, b in zip(cuts, cuts[1:]):
            # Seconds a+1..b: on for all of them means t0 <= a and t1 >= b.
            on = [(pid, team) for t0, t1, pid, team in shifts if t0 <= a and t1 >= b]
            sk = {t: sorted(p for p, tm in on if tm == t and p not in goalies) for t in teams}
            if not all(any(p in goalies and tm == t for p, tm in on) for t in teams):
                continue
            if all(len(v) == 5 for v in sk.values()):
                out.extend((t, tuple(sk[t]), b - a) for t in teams)
    return out
