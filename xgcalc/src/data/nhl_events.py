"""
Shots from the raw NHL feed, with every feature the public data can support.
===========================================================================

clean.py turns MoneyPuck's shot rows into the model table. This module builds
the same kind of table straight from the NHL's own play-by-play and shift
chart (the files nhl_backfill.py caches), so the model that scores tonight's
game is trained on exactly the feed it will be fed. Column names and meanings
match clean.py wherever both have the column; everything below the "beyond
MoneyPuck" markers is new.

What the public feed has, and what we derive from it
----------------------------------------------------
The play-by-play logs shots (all four results, blocked included), faceoffs,
hits, giveaways, takeaways, penalties and stoppages, each with rink
coordinates, a clock time and the team that made it. It does NOT log passes
or zone entries, so royal-road passes and true rushes are invisible. What we
can see is the trail of events before a shot, and that is what the sequence
features below are built from:

  rush proxies      seconds since the play was last outside the offensive
                    zone; seconds since the shooting team won the puck
  lateral proxies   how far across the ice the puck moved from the previous
                    event, and whether it crossed the middle, per second
  rebounds          split by what came before: a save, a miss or a block

The shift chart says who was on the ice, which gives fatigue (how long the
shooter and both units had been out) and the on-ice skaters for player
stats later.

Frames
------
Coordinates are flipped per (team, period) so the shooting team always
attacks the net at x = +89, as in clean.py; y is flipped with x (a 180°
rotation, MoneyPuck's convention), so off_wing matches theirs. Which end a
team attacks is read from homeTeamDefendingSide when the feed carries it
(2019+ only) and otherwise inferred from the zone codes every located event
carries: an event in a team's offensive zone sits at the end it attacks.
"""

import math
from datetime import date

GOAL_LINE_X = 89.0
BLUE_LINE_X = 25.0
PULL_TIME_SECONDS = 3000  # same rule as clean.py

SHOT_EVENTS = {"goal": "GOAL", "shot-on-goal": "SHOT", "missed-shot": "MISS",
               "blocked-shot": "BLOCK"}
EVENT_CODE = {**SHOT_EVENTS, "faceoff": "FAC", "hit": "HIT", "giveaway": "GIVE",
              "takeaway": "TAKE", "penalty": "PENL", "delayed-penalty": "DELPEN",
              "stoppage": "STOP", "period-start": "PSTR", "period-end": "PEND",
              "game-end": "GEND"}
SHOT_TYPE = {"wrist": "WRIST", "snap": "SNAP", "slap": "SLAP", "backhand": "BACK",
             "tip-in": "TIP", "deflected": "DEFL", "wrap-around": "WRAP"}
POSITION = {"C": "C", "L": "L", "R": "R", "D": "D", "G": "G"}

FIXED_SITUATIONS = {(5, 5): "EV_5v5", (5, 4): "PP_5v4", (4, 5): "SH_4v5", (4, 4): "EV_4v4",
                    (3, 3): "EV_3v3", (5, 3): "PP_5v3", (4, 3): "PP_4v3"}


def _mmss(t):
    m, s = t.split(":")
    return int(m) * 60 + int(s)


def _zone(x_adj):
    if x_adj is None:
        return "NONE"
    return "OFF" if x_adj > BLUE_LINE_X else "NEU" if x_adj >= -BLUE_LINE_X else "DEF"


def _attack_signs(plays, home_id, away_id):
    """{(team_id, period): +1 or -1}, the sign of x at the net that team attacks."""
    signs = {}
    for x in plays:
        d = x.get("homeTeamDefendingSide")
        p = x["periodDescriptor"]["number"]
        if d in ("left", "right") and (home_id, p) not in signs:
            s = 1 if d == "left" else -1
            signs[(home_id, p)], signs[(away_id, p)] = s, -s
    votes = {}
    for x in plays:
        d = x.get("details") or {}
        team, zone, xc = d.get("eventOwnerTeamId"), d.get("zoneCode"), d.get("xCoord")
        if team is None or xc in (None, 0) or zone not in ("O", "D"):
            continue
        s = (1 if xc > 0 else -1) * (1 if zone == "O" else -1)
        votes[(team, x["periodDescriptor"]["number"])] = \
            votes.get((team, x["periodDescriptor"]["number"]), 0) + s
    for (team, p), v in votes.items():
        if (team, p) in signs or v == 0:
            continue
        other = away_id if team == home_id else home_id
        if (other, p) in signs:  # already set from the other side
            continue
        signs[(team, p)], signs[(other, p)] = (1, -1) if v > 0 else (-1, 1)
    return signs


def _situation(sk, opp_sk, own_goalie, opp_goalie, trailing, game_sec, prev_code):
    """clean.py's situation buckets. Skater counts include an extra attacker."""
    if not opp_goalie:
        return "EN_AGAINST"
    if not own_goalie:
        pulled = trailing and game_sec >= PULL_TIME_SECONDS and prev_code != "DELPEN"
        if (sk, opp_sk) == (6, 5):
            return "EN_6v5_PULLED" if pulled else "EN_6v5_DELAYED_PEN"
        return "EN_OTHER_PULLED" if pulled else "EN_OTHER_DELAYED_PEN"
    if (sk, opp_sk) in FIXED_SITUATIONS:
        return FIXED_SITUATIONS[(sk, opp_sk)]
    return "PP_OTHER" if sk > opp_sk else "SH_OTHER" if sk < opp_sk else "OTHER"


def _age(birth, game_date):
    try:
        b, g = date.fromisoformat(birth), date.fromisoformat(game_date)
    except (TypeError, ValueError):
        return None
    return round((g - b).days / 365.25, 2)


class _Shifts:
    """Who was on the ice at a given (period, second), and for how long."""

    def __init__(self, shifts, goalies):
        self.by_period = {}
        for s in shifts:
            if s.get("typeCode") != 517 or not s.get("startTime") or not s.get("endTime"):
                continue
            t0, t1 = _mmss(s["startTime"]), _mmss(s["endTime"])
            if t1 <= t0:
                continue
            self.by_period.setdefault(s["period"], []).append(
                (t0, t1, s["playerId"], s["teamId"], s["playerId"] in goalies))
        self.ok = bool(self.by_period)

    def on_ice(self, period, t):
        """[(player_id, team_id, is_goalie, seconds_into_shift)]. A player whose
        shift ends at t was on for an event at t; one starting at t was not."""
        return [(pid, team, g, t - t0) for t0, t1, pid, team, g in self.by_period.get(period, ())
                if t0 < t <= t1 or (t0 == t == 0)]


def game_shots(pbp, shifts_doc, bios):
    """One row (a dict) per shot attempt in one game, blocked shots included.

    bios: {player_id: {"hand", "birth", "height"}} for the season.
    Returns (rows, report) where report counts what was skipped and why.
    """
    gid = pbp["id"]
    home, away = pbp["homeTeam"], pbp["awayTeam"]
    home_id, away_id = home["id"], away["id"]
    abbrev = {home_id: home["abbrev"], away_id: away["abbrev"]}
    playoff = pbp.get("gameType") == 3
    game_date = pbp.get("gameDate", "")
    roster = {r["playerId"]: r for r in pbp.get("rosterSpots", [])}
    team_of = {pid: r["teamId"] for pid, r in roster.items()}
    goalies = {pid for pid, r in roster.items() if r.get("positionCode") == "G"}
    shifts = _Shifts((shifts_doc or {}).get("data", []), goalies)

    plays = [x for x in pbp.get("plays", [])
             if x["periodDescriptor"].get("periodType") != "SO"]
    plays.sort(key=lambda x: x["sortOrder"])
    signs = _attack_signs(plays, home_id, away_id)
    report = {"shots": 0, "no_coords": 0, "no_direction": 0, "penalty_shot": 0}

    def owner(x):
        d = x.get("details") or {}
        if x["typeDescKey"] in SHOT_EVENTS:
            sh = d.get("scoringPlayerId") or d.get("shootingPlayerId")
            if sh in team_of:
                return team_of[sh]
            if x["typeDescKey"] == "blocked-shot":  # owner is the blocking team
                o = d.get("eventOwnerTeamId")
                return away_id if o == home_id else home_id if o == away_id else None
        return d.get("eventOwnerTeamId")

    # One pass to give every play its time, owner and raw coords.
    ev = []
    for x in plays:
        d = x.get("details") or {}
        p = x["periodDescriptor"]["number"]
        t = _mmss(x["timeInPeriod"])
        ev.append({"p": p, "t": t, "g": (p - 1) * 1200 + t,
                   "code": EVENT_CODE.get(x["typeDescKey"], x["typeDescKey"].upper()),
                   "team": owner(x), "x": d.get("xCoord"), "y": d.get("yCoord"),
                   "raw": x, "d": d})

    rows = []
    home_goals = away_goals = 0
    last_fac_g = 0
    for i, e in enumerate(ev):
        if e["code"] == "FAC":
            last_fac_g = e["g"]
        if e["code"] not in ("GOAL", "SHOT", "MISS", "BLOCK"):
            continue
        d, x = e["d"], e["raw"]
        team = e["team"]
        if team not in (home_id, away_id):
            continue
        is_home = team == home_id
        score_before = (home_goals, away_goals)
        if e["code"] == "GOAL":
            home_goals = d.get("homeScore", home_goals + is_home)
            away_goals = d.get("awayScore", away_goals + (not is_home))

        code = x.get("situationCode") or "1551"
        if len(code) != 4 or not code.isdigit():
            code = "1551"
        ag, ask, hsk, hg = (int(c) for c in code)
        sk, opp_sk = (hsk, ask) if is_home else (ask, hsk)
        own_g, opp_g = (hg, ag) if is_home else (ag, hg)
        if sk <= 1 and opp_sk == 0:  # penalty shot: one skater, no defenders
            report["penalty_shot"] += 1
            continue
        report["shots"] += 1
        if e["x"] is None or e["y"] is None:
            report["no_coords"] += 1
            continue
        sign = signs.get((team, e["p"]))
        if sign is None:
            report["no_direction"] += 1
            continue

        def adj(ex):
            if ex["x"] is None or ex["y"] is None:
                return None, None
            return float(ex["x"]) * sign, float(ex["y"]) * sign

        xa, ya = adj(e)
        dx = GOAL_LINE_X - xa
        distance = math.hypot(dx, ya)
        angle = math.degrees(math.atan2(abs(ya), dx))

        # --- previous events -------------------------------------------------
        prev = ev[i - 1] if i > 0 and ev[i - 1]["p"] == e["p"] else None
        prev2 = ev[i - 2] if i > 1 and ev[i - 2]["p"] == e["p"] else None
        pcode = prev["code"] if prev else "NONE"
        px, py = adj(prev) if prev else (None, None)
        dt = e["t"] - prev["t"] if prev else None
        dist_prev = math.hypot(xa - px, ya - py) if px is not None else None
        same_team_prev = int(bool(prev) and prev["team"] == team)
        reb_from = pcode if (prev and same_team_prev and pcode in ("SHOT", "MISS", "BLOCK")
                             and dt is not None and dt <= 3) else "NONE"
        prev_angle_change = None
        if reb_from != "NONE" and px is not None:
            prev_angle = math.degrees(math.atan2(py, GOAL_LINE_X - px))
            prev_angle_change = abs(math.degrees(math.atan2(ya, dx)) - prev_angle)

        # Rush proxies: walk back through this period's events.
        since_non_oz = since_won = None
        for j in range(i - 1, -1, -1):
            q = ev[j]
            if q["p"] != e["p"] or e["t"] - q["t"] > 60:
                break
            if since_non_oz is None:
                qx, _ = adj(q)
                if qx is not None and qx <= BLUE_LINE_X:
                    since_non_oz = e["t"] - q["t"]
            if since_won is None:
                won = ((q["code"] == "TAKE" and q["team"] == team)
                       or (q["code"] == "GIVE" and q["team"] not in (team, None))
                       or (q["code"] in ("SHOT", "MISS", "BLOCK", "GOAL") and q["team"] not in (team, None))
                       or (q["code"] == "FAC"))
                if won:
                    since_won = e["t"] - q["t"]
            if since_non_oz is not None and since_won is not None:
                break

        # --- shooter, goalie and the people on the ice -------------------------
        shooter = d.get("scoringPlayerId") or d.get("shootingPlayerId")
        bio = bios.get(shooter, {})
        hand = bio.get("hand") or "U"
        pos = POSITION.get((roster.get(shooter) or {}).get("positionCode"), "U")
        off_wing = int((hand == "L" and ya <= 0) or (hand == "R" and ya > 0))

        on = shifts.on_ice(e["p"], e["t"]) if shifts.ok else []
        mine = [r for r in on if r[1] == team and not r[2]]
        theirs = [r for r in on if r[1] != team and not r[2]]
        shooter_shift = next((r[3] for r in mine if r[0] == shooter), None)

        def mean(v):
            return round(sum(v) / len(v), 1) if v else None

        lead = (score_before[0] - score_before[1]) * (1 if is_home else -1)
        sit = _situation(sk, opp_sk, own_g, opp_g, lead < 0, e["g"], pcode)
        eff_sk, eff_opp = sk - (1 - own_g), opp_sk - (1 - opp_g)
        tp = SHOT_TYPE.get(d.get("shotType"))

        rows.append({
            # identifiers
            "game_id": gid, "season": gid // 1_000_000, "event_id": x["eventId"],
            "sort_order": x["sortOrder"], "game_date": game_date,
            "event": e["code"], "is_playoff": int(playoff),
            "team": abbrev[team], "home_team": home["abbrev"], "away_team": away["abbrev"],
            "venue": (pbp.get("venue") or {}).get("default"),
            # time
            "period": e["p"], "time_seconds": e["g"],
            "time_since_faceoff": e["g"] - last_fac_g,
            "is_overtime": int(e["p"] >= 4),
            "period_format": "REGULATION" if e["p"] <= 3 else "OT_5v5" if playoff else "OT_3v3",
            # coordinates and geometry
            "x_raw": float(e["x"]), "y_raw": float(e["y"]), "x_adj": xa, "y_adj": ya,
            "y_abs": abs(ya), "distance": distance, "angle_from_net": angle,
            "is_behind_net": int(xa > GOAL_LINE_X), "zone_code": d.get("zoneCode"),
            # the shot
            "shot_type": tp or "UNKNOWN", "shot_type_missing": int(tp is None),
            # sequence (MoneyPuck-equivalent)
            "prev_event": pcode, "prev_event_x": px, "prev_event_y": py,
            "prev_event_zone": _zone(px), "time_since_last_event": dt,
            "distance_from_last_event": dist_prev,
            "speed_from_last_event": (dist_prev / max(dt, 1)) if dist_prev is not None else None,
            "is_rebound": int(reb_from != "NONE"),
            # --- beyond MoneyPuck: sequence ---
            "prev_same_team": same_team_prev,
            "prev2_event": prev2["code"] if prev2 else "NONE",
            "time_since_prev2": (e["t"] - prev2["t"]) if prev2 else None,
            "rebound_from": reb_from,
            "rebound_angle_change": prev_angle_change,
            "secs_since_non_oz": since_non_oz, "secs_since_won_puck": since_won,
            "lateral_dy": (ya - py) if py is not None else None,
            "crossed_middle": int(py is not None and dt is not None and dt <= 3
                                  and ya * py < 0 and abs(ya - py) >= 10),
            # strength
            "is_home": int(is_home), "shooting_skaters": sk, "defending_skaters": opp_sk,
            "skater_differential": sk - opp_sk, "strength_state": f"{sk}v{opp_sk}",
            "is_empty_net": int(not opp_g), "shooter_net_empty": int(not own_g),
            "pulled_goalie_state": int(not opp_g or not own_g),
            "strength_bucket": "PP" if eff_sk > eff_opp else "SH" if eff_sk < eff_opp else "EV",
            "situation": sit,
            # shooter and goalie
            "shooter_id": shooter, "shooter_hand": hand, "shooter_position": pos,
            "off_wing": off_wing, "shooter_age": _age(bio.get("birth"), game_date),
            "shooter_height": bio.get("height"),
            "goalie_id": d.get("goalieInNetId"),
            "blocker_id": d.get("blockingPlayerId"),
            "assist1_id": d.get("assist1PlayerId"), "assist2_id": d.get("assist2PlayerId"),
            # score
            "score_differential": lead,
            # --- beyond MoneyPuck: shifts ---
            "has_shifts": int(shifts.ok),
            "shooter_shift_secs": shooter_shift,
            "shoot_avg_shift_secs": mean([r[3] for r in mine]),
            "def_avg_shift_secs": mean([r[3] for r in theirs]),
            "def_max_shift_secs": max((r[3] for r in theirs), default=None),
            "shoot_on_ice": ",".join(str(r[0]) for r in mine),
            "def_on_ice": ",".join(str(r[0]) for r in theirs),
            # label
            "goal": int(e["code"] == "GOAL"),
            "was_on_goal": int(e["code"] in ("GOAL", "SHOT")),
        })
    return rows, report
