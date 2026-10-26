#!/usr/bin/env python3
"""Turn an NHL game into a Rinkside tracker backup: every shot attempt with
its rink coordinates, plus one team's shift chart as line changes, so the
tracker derives TOI, on-ice xGF/xGA and the report exactly as if the game had
been tagged live.

Two public NHL endpoints, both updated within seconds during a game:
  api-web.nhle.com/v1/gamecenter/{id}/play-by-play   shots, coordinates, strength
  api.nhle.com/stats/rest/en/shiftcharts             who was on the ice
Neither sends CORS headers, so the browser can't call them: web/serve.py
proxies this module at /nhl/..., and the CLI writes a file for Import backup.

The tracker keeps one roster ("us"), so shifts and TOI are for the chosen
team; shots are logged for both. Stdlib only: serve.py runs on system python.

  python3 nhl_game.py --date 2026-10-18             list that day's games
  python3 nhl_game.py 2026020135 --team MIN         write the backup JSON
"""
import argparse, json, sys, time, urllib.request

PBP = "https://api-web.nhle.com/v1/gamecenter/{}/play-by-play"
SHIFTS = "https://api.nhle.com/stats/rest/en/shiftcharts?cayenneExp=gameId={}"
SCORE = "https://api-web.nhle.com/v1/score/{}"

RESULT = {"goal": "GOAL", "shot-on-goal": "SAVE", "missed-shot": "MISS", "blocked-shot": "BLOCK"}
# The tracker merges wrist and snap; bats, pokes and between-the-legs have no bucket.
SHOT_TYPE = {"wrist": "WRIST", "snap": "WRIST", "slap": "SLAP", "backhand": "BACK",
             "tip-in": "TIP", "deflected": "DEFL", "wrap-around": "WRAP"}
POS = {"C": "F", "L": "F", "R": "F", "D": "D", "G": "G"}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "rinkside-tracker/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def mmss(t):
    m, s = t.split(":")
    return int(m) * 60 + int(s)


def list_games(date):
    """[{id, away, home, state, label}] for one date (YYYY-MM-DD)."""
    out = []
    for g in get(SCORE.format(date)).get("games", []):
        a, h = g["awayTeam"]["abbrev"], g["homeTeam"]["abbrev"]
        out.append({"id": g["id"], "away": a, "home": h, "state": g["gameState"],
                    "label": f"{a} @ {h}"})
    return out


PULL_TIME_SECONDS = 3000  # src/data/clean.py: a pull is trailing and late


def situation(sk, opp_sk, g, opp_g, trailing, game_sec):
    """The model's situation bucket from the shooter's side, as clean.py
    builds it. Skater counts include any extra attacker, like the feed's."""
    if not opp_g:
        return "EN_AGAINST"
    if not g:
        pulled = trailing and game_sec >= PULL_TIME_SECONDS
        if (sk, opp_sk) == (6, 5):
            return "EN_6v5_PULLED" if pulled else "EN_6v5_DELAYED_PEN"
        return "EN_OTHER_PULLED" if pulled else "EN_OTHER_DELAYED_PEN"
    fixed = {(5, 5): "EV_5v5", (5, 4): "PP_5v4", (4, 5): "SH_4v5", (4, 4): "EV_4v4", (3, 3): "EV_3v3",
             (5, 3): "PP_5v3", (4, 3): "PP_4v3"}
    if (sk, opp_sk) in fixed:
        return fixed[(sk, opp_sk)]
    return "PP_OTHER" if sk > opp_sk else "SH_OTHER" if sk < opp_sk else "OTHER"


def team_name(t):
    return f'{t["placeName"]["default"]} {t["commonName"]["default"]}'


def build_backup(game_id, team=None, pbp=None, shifts=None):
    """Return {"setup", "game", "summary"} in the tracker's backup format.
    team is an abbrev (default: home). pbp/shifts can be passed for tests."""
    pbp = pbp if pbp is not None else get(PBP.format(game_id))
    shifts = shifts if shifts is not None else get(SHIFTS.format(game_id)).get("data", [])
    home, away = pbp["homeTeam"], pbp["awayTeam"]
    team = (team or home["abbrev"]).upper()
    if team not in (home["abbrev"], away["abbrev"]):
        raise ValueError(f"{team} isn't in this game ({away['abbrev']} @ {home['abbrev']})")
    us, them = (home, away) if team == home["abbrev"] else (away, home)
    us_home = us is home

    playoff = pbp.get("gameType") == 3
    per_len = 20 * 60
    ot_len = (20 if playoff else 5) * 60
    plen = lambda p: per_len if p <= 3 else ot_len

    team_of = {r["playerId"]: r["teamId"] for r in pbp["rosterSpots"]}
    roster = sorted(({"num": str(r["sweaterNumber"]),
                      "name": f'{r["firstName"]["default"][0]}. {r["lastName"]["default"]}',
                      "pos": POS.get(r["positionCode"], "F")}
                     for r in pbp["rosterSpots"] if r["teamId"] == us["id"]),
                    key=lambda r: int(r["num"]))
    num_of = {r["playerId"]: str(r["sweaterNumber"]) for r in pbp["rosterSpots"]}

    plays = [x for x in pbp["plays"] if x["periodDescriptor"].get("periodType") != "SO"]

    # Ends: the tracker alternates from P1 and records exceptions as flips.
    side = {}
    for x in plays:
        d = x.get("homeTeamDefendingSide")
        if d in ("left", "right"):
            side.setdefault(x["periodDescriptor"]["number"], (d == "left") == us_home)
    us_right_p1 = side.get(1, True)
    flips = []
    for p in sorted(side):
        cur = (us_right_p1 == (p % 2 == 1)) != (len([q for q in flips if q <= p]) % 2 == 1)
        if cur != side[p]:
            flips.append(p)

    base = int(time.time() * 1000) - 10_000_000  # synthetic wall times keep events ordered
    nid = 1
    shots, skipped, score = [], 0, (0, 0)  # score is (away, home) before each shot
    for x in plays:
        kind = RESULT.get(x["typeDescKey"])
        d = x.get("details") or {}
        if not kind:
            continue
        if d.get("xCoord") is None or d.get("yCoord") is None:
            skipped += 1
            continue
        shooter = d.get("scoringPlayerId") or d.get("shootingPlayerId")
        # A blocked shot is owned by the blocking team, so go by the shooter.
        tid = team_of.get(shooter, d.get("eventOwnerTeamId"))
        mine = tid == us["id"]
        p = x["periodDescriptor"]["number"]
        el = mmss(x["timeInPeriod"])
        code = x.get("situationCode") or "1551"
        ag, ask, hsk, hg = (int(c) for c in code) if len(code) == 4 else (1, 5, 5, 1)
        shooter_home = tid == home["id"]
        lead = (score[1] - score[0]) * (1 if shooter_home else -1)
        sit = situation(*((hsk, ask, hg, ag) if shooter_home else (ask, hsk, ag, hg)),
                        trailing=lead < 0, game_sec=(p - 1) * per_len + el)
        # The dropdown's strength is from our side whoever shoots, net of any
        # extra attacker; sit above is the exact bucket the model trained on.
        a, b = (hsk - (1 - hg), ask - (1 - ag)) if us_home else (ask - (1 - ag), hsk - (1 - hg))
        diff = a - b
        st = "EV" if diff == 0 else ("PP2" if diff >= 2 else "PP") if diff > 0 else ("PK2" if diff <= -2 else "PK")
        if kind == "GOAL":
            score = (d.get("awayScore", score[0]), d.get("homeScore", score[1]))
        shots.append({"id": nid, "w": base + x["sortOrder"] * 10, "p": p, "s": plen(p) - el, "sit": sit,
                      "x": float(d["xCoord"]), "y": float(d["yCoord"]),
                      "team": "us" if mine else "them",
                      "type": SHOT_TYPE.get(d.get("shotType"), "UNKNOWN"), "result": kind,
                      "reb": None, "rush": False, "xi": False, "offd": False, "str": st,
                      "who": num_of.get(shooter, ""), "nhl": x["eventId"]})
        nid += 1

    # Shift chart -> line changes. Everyone leaving and arriving at one
    # instant is one change; a change sorts after the plays at that second
    # (a goal's on-ice is the group that scored, not the next one out).
    last_sort = {}
    for x in plays:
        k = (x["periodDescriptor"]["number"], mmss(x["timeInPeriod"]))
        last_sort[k] = max(last_sort.get(k, 0), x["sortOrder"])
    sorts = sorted(last_sort.items())

    def sort_at(p, el):
        best = 0
        for (q, t), so in sorts:
            if (q, t) <= (p, el):
                best = so
            else:
                break
        return best

    instants = {}
    mine_shifts = [s for s in shifts if s.get("typeCode") == 517 and s["teamId"] == us["id"]
                   and s.get("startTime") and s.get("endTime")]
    for s in mine_shifts:
        n = num_of.get(s["playerId"])
        if not n:
            continue
        p, t0, t1 = s["period"], mmss(s["startTime"]), mmss(s["endTime"])
        if t1 <= t0:
            continue
        instants.setdefault((p, t0), {"on": [], "off": []})["on"].append(n)
        instants.setdefault((p, t1), {"on": [], "off": []})["off"].append(n)
    changes = []
    for (p, el), c in sorted(instants.items()):
        # Back-to-back shifts for one player (split at a goal) cancel out.
        both = set(c["on"]) & set(c["off"])
        on = sorted((n for n in c["on"] if n not in both), key=int)
        off = sorted((n for n in c["off"] if n not in both), key=int)
        if not on and not off:
            continue
        changes.append({"id": nid, "w": base + sort_at(p, el) * 10 + 5, "p": p,
                        "s": plen(p) - el, "off": off, "on": on})
        nid += 1

    # Clock: stopped where the feed is, so open shifts end there.
    pd = pbp.get("periodDescriptor") or {}
    end_p = pd.get("number") or (plays[-1]["periodDescriptor"]["number"] if plays else 1)
    if pd.get("periodType") == "SO":
        end_p, end_s = end_p - 1, 0
    else:
        end_s = (pbp.get("clock") or {}).get("secondsRemaining", 0)
    clock = [{"w": base, "k": "set", "p": 1, "s": plen(1)},
             {"w": base + 9_000_000, "k": "set", "p": end_p, "s": end_s}]

    setup = {"date": pbp.get("gameDate", ""), "us": team_name(us), "opp": team_name(them),
             "periodMin": per_len // 60, "otMin": ot_len // 60, "otFormat": "5v5" if playoff else "3v3",
             "usRightP1": us_right_p1, "roster": roster,
             "lines": {k: [] for k in ["f1", "f2", "f3", "f4", "d1", "d2", "d3", "p1", "p2"]},
             "nhl": {"game": pbp["id"], "team": team}}
    game = {"clock": clock, "strength": "EV", "shots": shots, "changes": changes, "flips": flips,
            "nextId": nid}
    summary = {"game": pbp["id"], "state": pbp.get("gameState"), "team": team,
               "label": f'{away["abbrev"]} @ {home["abbrev"]}', "shots": len(shots),
               "changes": len(changes), "shifts": len(mine_shifts), "skipped": skipped}
    return {"setup": setup, "game": game, "summary": summary}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("game", nargs="?", type=int, help="NHL game id, e.g. 2026020135")
    ap.add_argument("--team", help="abbrev of the team whose shifts to load (default: home)")
    ap.add_argument("--date", help="list the games on this date instead")
    ap.add_argument("-o", "--out", help="output path (default: <date>_<team>_nhl_backup.json)")
    a = ap.parse_args()
    if a.date:
        for g in list_games(a.date):
            print(g["id"], g["label"], g["state"])
        return
    if not a.game:
        ap.error("give a game id, or --date to list games")
    b = build_backup(a.game, a.team)
    sm = b["summary"]
    out = a.out or f'{b["setup"]["date"]}_{sm["team"]}_nhl_backup.json'
    with open(out, "w") as f:
        json.dump({"setup": b["setup"], "game": b["game"]}, f)
    print(f'{sm["label"]} ({sm["state"]}): {sm["shots"]} shots, {sm["shifts"]} {sm["team"]} shifts '
          f'-> {sm["changes"]} changes. Wrote {out}; load it with Setup > Import backup.')
    if not sm["shifts"]:
        print("No shift chart yet (it often lags live games); TOI stays empty until it's published.",
              file=sys.stderr)


if __name__ == "__main__":
    main()
