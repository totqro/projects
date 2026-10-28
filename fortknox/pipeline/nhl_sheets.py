#!/usr/bin/env python3
"""Build the game-sheet data for one season: every final game scored with
the full-data xG model, plus season tables for teams, skaters and goalies.

  python nhl_sheets.py                       the current season, into ../data/ (the site reads it)
  python nhl_sheets.py --season 2025 --out /tmp/sheets
  python nhl_sheets.py --no-fetch            use only what's already cached

Fetches any newly final games first (nhl_backfill.py), so the nightly job is
this one command. Writes, under --out/{season}/:

  index.json            every game: teams, score, xG, attempts
  games/{game_id}.json  one game: shots (compact rows) and a player table
  teams.json            season totals and 5v5 / PP / PK rates per team
  players.json          skaters (individual, on-ice and off-ice) and goalies (GSAx)
  lines.json            5v5 forward lines, defence pairs and every pair of teammates

and refreshes --out/seasons.json, the list of seasons present, newest first.

Blocked shots are listed as attempts with no xG, like MoneyPuck: the model is
fitted on unblocked shots, and a block's coordinates are where it was
blocked, not where it was taken.
"""
import argparse
import gzip
import json
import sys
from collections import defaultdict
from itertools import combinations
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import nhl_backfill  # noqa: E402
from build_nhl_dataset import load_bios  # noqa: E402
from src.data.nhl_events import game_shots  # noqa: E402
from src.data.nhl_toi import STATES, game_toi  # noqa: E402
from src.data.nhl_units import game_units  # noqa: E402

MODEL_PATH = ROOT / "data" / "nhl_xg_model.joblib"
# Each shooter's finishing baseline by season (fit_shooter_baseline.py).
BASELINE_PATH = ROOT / "data" / "shooter_baseline.json"
CACHE = nhl_backfill.CACHE
OUT = ROOT.parent / "data"   # fortknox/data, where the site build reads the sheets

# Compact shot rows in games/{id}.json; the key order is in the file too.
SHOT_KEYS = ["p", "t", "team", "ev", "x", "y", "type", "xg", "shooter", "goalie", "sit",
             "reb", "rush", "ast"]


def current_season(today=None):
    d = today or datetime.now(timezone.utc).date()
    return d.year if d.month >= 9 else d.year - 1


def _load(p):
    with gzip.open(p, "rt") as f:
        return json.load(f)


def name_of(r):
    return f'{r["firstName"]["default"]} {r["lastName"]["default"]}'


def r1(v):
    return round(float(v), 3)


def shooter_baseline(season):
    """GAx per unblocked shot each shooter's history says to expect in
    `season`, by player id; None for a season the file doesn't cover."""
    if not BASELINE_PATH.exists():
        return None
    s = json.loads(BASELINE_PATH.read_text())["seasons"].get(str(season))
    return {int(k): v for k, v in s["rate"].items()} if s else None


def build(season, root, fetch, cache=None):
    """`cache` replaces the raw-feed cache (nhl_live.py points it at tonight's
    games in progress)."""
    out = root / str(season)
    if fetch:
        nhl_backfill.backfill_season(season, workers=6, refresh_bios=True)
    d = (cache or CACHE) / str(season)
    bios = load_bios(d)
    model = joblib.load(MODEL_PATH)

    games = []
    for f in sorted(d.glob("*.pbp.json.gz")):
        pbp = _load(f)
        sh_path = Path(str(f).replace(".pbp.", ".shifts."))
        shifts = _load(sh_path) if sh_path.exists() else None
        rows, _ = game_shots(pbp, shifts, bios)
        games.append((pbp, shifts, rows))

    shots = pd.DataFrame([r for _, _, rows in games for r in rows])
    unblocked = shots.event != "BLOCK"
    shots["xg"] = 0.0
    shots.loc[unblocked, "xg"] = model.predict(shots[unblocked])
    by_game = {g: part for g, part in shots.groupby("game_id")}
    # The shots a finishing baseline counts (unblocked, not at an empty net),
    # per shooter and phase, for each skater's expected GAx.
    fin = shots[unblocked & (shots.situation != "EN_AGAINST") & shots.shooter_id.notna()]
    fin_shots = {ph: fin[fin.is_playoff == (ph == "playoff")].groupby("shooter_id").size().to_dict()
                 for ph in ("regular", "playoff")}
    base = shooter_baseline(season)

    (out / "games").mkdir(parents=True, exist_ok=True)
    index = []
    # Season tables are kept apart by game type: playoff games would
    # otherwise pad some teams' and players' totals and not others'.
    agg_of = lambda: defaultdict(lambda: defaultdict(float))
    teams_by, skaters_by, goalies_by, units_by = ({"regular": agg_of(), "playoff": agg_of()} for _ in range(4))
    info = {}

    for pbp, shifts, _ in games:
        gid = pbp["id"]
        phase = "playoff" if pbp.get("gameType") == 3 else "regular"
        teams, skaters, goalies, units = teams_by[phase], skaters_by[phase], goalies_by[phase], units_by[phase]
        sh = by_game.get(gid, shots.iloc[0:0])
        home, away = pbp["homeTeam"], pbp["awayTeam"]
        ab = {home["id"]: home["abbrev"], away["id"]: away["abbrev"]}
        roster = {r["playerId"]: r for r in pbp.get("rosterSpots", [])}
        p_toi, t_toi = game_toi(pbp, shifts)
        last = (pbp.get("gameOutcome") or {}).get("lastPeriodType", "REG")

        def side(abbrev):
            mine, theirs = sh[sh.team == abbrev], sh[sh.team != abbrev]
            return {"xg": r1(mine.xg.sum()), "xg5": r1(mine[mine.situation == "EV_5v5"].xg.sum()),
                    "att": int(len(mine)), "sog": int(mine.was_on_goal.sum()),
                    "xga": r1(theirs.xg.sum())}

        h, a = side(home["abbrev"]), side(away["abbrev"])
        hs, as_ = home.get("score", 0), away.get("score", 0)
        index.append({"id": gid, "date": pbp.get("gameDate"), "start": pbp.get("startTimeUTC"), "type": pbp.get("gameType"),
                      "home": home["abbrev"], "away": away["abbrev"], "hs": hs, "as": as_,
                      "end": last, "hxg": h["xg"], "axg": a["xg"], "hxg5": h["xg5"],
                      "axg5": a["xg5"], "hatt": h["att"], "aatt": a["att"],
                      "hsog": h["sog"], "asog": a["sog"], "shifts": bool(p_toi)})

        # --- team season totals ------------------------------------------------
        for tid, opp_id, gf, ga in ((home["id"], away["id"], hs, as_), (away["id"], home["id"], as_, hs)):
            t, me, op = teams[ab[tid]], ab[tid], ab[opp_id]
            t["gp"] += 1
            t["w"] += gf > ga
            t["l"] += gf < ga and last == "REG"
            t["otl"] += gf < ga and last != "REG"
            t["gf"] += gf
            t["ga"] += ga
            mine, theirs = sh[sh.team == me], sh[sh.team == op]
            t["xgf"] += mine.xg.sum()
            t["xga"] += theirs.xg.sum()
            t["cf"] += len(mine)
            t["ca"] += len(theirs)
            for st, sit_f, sit_a in (("5v5", "EV_5v5", "EV_5v5"), ("pp", "PP", "SH"),
                                     ("pk", "SH", "PP")):
                f = mine.situation.str.startswith(sit_f)
                g = theirs.situation.str.startswith(sit_a)
                t[f"xgf_{st}"] += mine[f].xg.sum()
                t[f"xga_{st}"] += theirs[g].xg.sum()
                t[f"gf_{st}"] += mine[f].goal.sum()
                t[f"ga_{st}"] += theirs[g].goal.sum()
                t[f"cf_{st}"] += f.sum()
                t[f"ca_{st}"] += g.sum()
                if t_toi:
                    t[f"toi_{st}"] += t_toi[tid][st]
                    t[f"toi_gp_{st}"] += 1
            if t_toi:
                t["toi_all"] += t_toi[tid]["all"]

        # --- 5v5 units: lines, pairs, teammates ----------------------------------
        pos_of = {pid: r["positionCode"] for pid, r in roster.items()}
        for tid, ids, secs in game_units(pbp, shifts):
            for key in unit_keys(ab[tid], ids, pos_of):
                units[key]["toi"] += secs
        ev5 = sh[sh.situation == "EV_5v5"]
        for row in ev5.itertuples():
            opp = away["abbrev"] if row.team == home["abbrev"] else home["abbrev"]
            for ids, team, fa in ((row.shoot_on_ice, row.team, "f"), (row.def_on_ice, opp, "a")):
                for key in unit_keys(team, [int(s) for s in (ids or "").split(",") if s], pos_of):
                    u = units[key]
                    u[f"xg{fa}"] += row.xg
                    u[f"g{fa}"] += row.goal
                    u[f"c{fa}"] += 1
        # Each team's 5v5 totals for the game, for every player's off-ice numbers.
        team5 = {}
        for tid in (home["id"], away["id"]):
            mine, theirs = ev5[ev5.team == ab[tid]], ev5[ev5.team != ab[tid]]
            team5[tid] = {"toi5": t_toi[tid]["5v5"] if t_toi else 0, "xgf5": mine.xg.sum(), "xga5": theirs.xg.sum(),
                          "gf5": mine.goal.sum(), "ga5": theirs.goal.sum()}

        # --- players -------------------------------------------------------------
        game_players = {}
        for pid, r in roster.items():
            info[pid] = {"name": name_of(r), "team": ab.get(r["teamId"]), "pos": r["positionCode"],
                         "num": r.get("sweaterNumber")}
            game_players[pid] = defaultdict(float)
        for row in sh.itertuples():
            if row.goal:
                for aid in (row.assist1_id, row.assist2_id):
                    if pd.notna(aid) and int(aid) in game_players:
                        game_players[int(aid)]["a"] += 1
            if row.shooter_id in game_players:
                gp = game_players[row.shooter_id]
                gp["att"] += 1
                gp["ixg"] += row.xg
                gp["g"] += row.goal
                gp["sog"] += row.was_on_goal
                if row.situation == "EV_5v5":
                    gp["ixg5"] += row.xg
                    gp["g5"] += row.goal
            for ids, fa in ((row.shoot_on_ice, "f"), (row.def_on_ice, "a")):
                for s in (ids or "").split(","):
                    if s and int(s) in game_players:
                        gp = game_players[int(s)]
                        gp[f"xg{fa}"] += row.xg
                        gp[f"g{fa}"] += row.goal
                        if row.situation == "EV_5v5":
                            gp[f"xg{fa}5"] += row.xg
                            gp[f"g{fa}5"] += row.goal
            if row.event != "BLOCK" and row.goalie_id in game_players and pd.notna(row.goalie_id):
                gk = game_players[int(row.goalie_id)]
                gk["sa"] += 1
                gk["ga_"] += row.goal
                gk["xga_"] += row.xg
        table = []
        for pid, gp in game_players.items():
            toi = p_toi.get(pid, {})
            if not toi and not gp:
                continue
            for st in STATES:
                gp[f"toi_{st}"] = toi.get(st, 0)
            r = info[pid]
            row = {"id": pid, "name": r["name"], "team": r["team"], "pos": r["pos"],
                   "num": r["num"], **{k: (r1(v) if "xg" in k else int(v)) for k, v in gp.items()}}
            table.append(row)
            agg = goalies[pid] if r["pos"] == "G" else skaters[pid]
            agg["gp"] += 1
            agg["toi_gp"] += bool(toi)
            for k, v in gp.items():
                agg[k] += v
            if toi.get("5v5") and roster[pid]["teamId"] in team5:
                for k, v in team5[roster[pid]["teamId"]].items():
                    agg[f"tm_{k}"] += v

        def shot_row(r):
            return [int(r.period), int(r.time_seconds - (r.period - 1) * 1200), r.team, r.event,
                    r.x_adj, r.y_adj, r.shot_type, round(float(r.xg), 4),
                    int(r.shooter_id) if pd.notna(r.shooter_id) else None,
                    int(r.goalie_id) if pd.notna(r.goalie_id) else None, r.situation,
                    r.rebound_from, int(pd.notna(r.secs_since_non_oz) and r.secs_since_non_oz <= 4),
                    [int(a) for a in (r.assist1_id, r.assist2_id) if pd.notna(a)] if r.event == "GOAL" else None]

        sheet = {"id": gid, "date": pbp.get("gameDate"), "type": pbp.get("gameType"),
                 "venue": (pbp.get("venue") or {}).get("default"), "end": last,
                 "home": {"abbrev": home["abbrev"], "name": nhl_team_name(home), "score": hs, **h},
                 "away": {"abbrev": away["abbrev"], "name": nhl_team_name(away), "score": as_, **a},
                 "shot_keys": SHOT_KEYS, "shots": [shot_row(r) for r in sh.itertuples()],
                 "players": table}
        (out / "games" / f"{gid}.json").write_text(json.dumps(sheet, separators=(",", ":")))

    index.sort(key=lambda g: (g["date"], g["id"]), reverse=True)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    write(out / "index.json", {"season": season, "updated": stamp, "games": index})
    write(out / "teams.json", {"season": season, "updated": stamp, **{
        ph: [team_row(k, v) for k, v in sorted(teams_by[ph].items())] for ph in teams_by}})
    write(out / "players.json", {"season": season, "updated": stamp, **{
        ph: {"skaters": [{**skater_row(pid, info[pid], v),
                          # The GAx his own history expects on this season's shots.
                          **({"gax_exp": round(base.get(pid, 0.0) * fin_shots[ph].get(pid, 0), 2)} if base else {})}
                         for pid, v in skaters_by[ph].items()],
             "goalies": [goalie_row(pid, info[pid], v) for pid, v in goalies_by[ph].items() if v["sa"]]}
        for ph in skaters_by}})
    write(out / "lines.json", {"season": season, "updated": stamp, **{
        ph: lines_tables(units_by[ph], info) for ph in units_by}})
    seasons = sorted((int(p.name) for p in root.iterdir()
                      if p.is_dir() and p.name.isdigit() and (p / "index.json").exists()),
                     reverse=True)
    write(root / "seasons.json", {"seasons": seasons, "updated": stamp})
    print(f"{season}: {len(index)} games, {int(unblocked.sum()):,} unblocked shots, "
          f"xG {shots.xg.sum():.0f} vs {int(shots.goal.sum())} goals -> {out}")


def unit_keys(team, ids, pos_of):
    """The groups a set of on-ice skaters counts toward: each skater alone
    ("S"), every pair of them ("P", for WOWY), the forward trio ("F") and
    the defence pair ("D") when there are exactly three and two."""
    ids = sorted(ids)
    fwd = tuple(i for i in ids if pos_of.get(i) in ("C", "L", "R"))
    dee = tuple(i for i in ids if pos_of.get(i) == "D")
    keys = [(team, "S", (i,)) for i in ids] + [(team, "P", p) for p in combinations(ids, 2)]
    if len(fwd) == 3:
        keys.append((team, "F", fwd))
    if len(dee) == 2:
        keys.append((team, "D", dee))
    return keys


# Units with less 5v5 time together than this are left out of lines.json.
MIN_UNIT_SECS = 60


def lines_tables(units, info):
    """lines.json for one phase: per team, its skaters' 5v5 totals with that
    team ("solo"), forward lines, defence pairs and every pair of teammates
    ("pairs"), each row [ids, toi, xgf, xga, gf, ga, cf, ca]."""
    out = defaultdict(lambda: {"players": {}, "solo": [], "fwd": [], "def": [], "pairs": []})
    name = {"S": "solo", "F": "fwd", "D": "def", "P": "pairs"}
    for (team, kind, ids), u in sorted(units.items(), key=lambda kv: -kv[1]["toi"]):
        if u["toi"] < MIN_UNIT_SECS and kind != "S":
            continue
        t = out[team]
        for i in ids:
            if i not in t["players"] and i in info:
                t["players"][i] = [info[i]["name"], info[i]["pos"]]
        t[name[kind]].append([list(ids), int(u["toi"]), r1(u["xgf"]), r1(u["xga"]), int(u["gf"]), int(u["ga"]),
                              int(u["cf"]), int(u["ca"])])
    return {k: out[k] for k in sorted(out)}


def nhl_team_name(t):
    place, common = t.get("placeName", {}).get("default"), t.get("commonName", {}).get("default")
    return f"{place} {common}" if place and common else t["abbrev"]


def per60(x, secs):
    return round(x * 3600 / secs, 3) if secs else None


def pct(a, b):
    return round(a / (a + b), 4) if a + b else None


def team_row(abbrev, t):
    out = {"team": abbrev, **{k: int(t[k]) for k in ("gp", "w", "l", "otl", "gf", "ga", "cf", "ca")},
           "pts": int(2 * t["w"] + t["otl"]), "xgf": r1(t["xgf"]), "xga": r1(t["xga"]),
           "xgf_pct": pct(t["xgf"], t["xga"]), "gsax_team": r1(t["xga"] - t["ga"])}
    for st in ("5v5", "pp", "pk"):
        toi = t[f"toi_{st}"]
        out[st] = {"toi": int(toi), "xgf": r1(t[f"xgf_{st}"]), "xga": r1(t[f"xga_{st}"]),
                   "gf": int(t[f"gf_{st}"]), "ga": int(t[f"ga_{st}"]),
                   "cf": int(t[f"cf_{st}"]), "ca": int(t[f"ca_{st}"]),
                   "xgf60": per60(t[f"xgf_{st}"], toi), "xga60": per60(t[f"xga_{st}"], toi),
                   "xgf_pct": pct(t[f"xgf_{st}"], t[f"xga_{st}"])}
    return out


def skater_row(pid, info, v):
    toi5 = v["toi_5v5"]
    return {"id": pid, **info, "gp": int(v["gp"]), "toi": int(v["toi_all"]), "toi5": int(toi5),
            "g": int(v["g"]), "a": int(v["a"]), "pts": int(v["g"] + v["a"]),
            "att": int(v["att"]), "sog": int(v["sog"]),
            "ixg": r1(v["ixg"]), "gax": r1(v["g"] - v["ixg"]),
            "ixg5": r1(v["ixg5"]), "g5": int(v["g5"]),
            "xgf5": r1(v["xgf5"]), "xga5": r1(v["xga5"]), "gf5": int(v["gf5"]), "ga5": int(v["ga5"]),
            "xgf_pct5": pct(v["xgf5"], v["xga5"]),
            "xgf": r1(v["xgf"]), "xga": r1(v["xga"]), "gf": int(v["gf"]), "ga": int(v["ga"]),
            "xgf_pct": pct(v["xgf"], v["xga"]),
            "xgf60_5": per60(v["xgf5"], toi5), "xga60_5": per60(v["xga5"], toi5),
            "ixg60_5": per60(v["ixg5"], toi5),
            # His teams' 5v5 numbers in his games while he was on the bench.
            "toi5_off": int(v["tm_toi5"] - toi5), "xgf5_off": r1(v["tm_xgf5"] - v["xgf5"]),
            "xga5_off": r1(v["tm_xga5"] - v["xga5"]), "gf5_off": int(v["tm_gf5"] - v["gf5"]),
            "ga5_off": int(v["tm_ga5"] - v["ga5"])}


def goalie_row(pid, info, v):
    return {"id": pid, **info, "gp": int(v["gp"]), "toi": int(v["toi_all"]), "sa": int(v["sa"]),
            "ga": int(v["ga_"]), "xga": r1(v["xga_"]), "gsax": r1(v["xga_"] - v["ga_"]),
            "sv_pct": round(1 - v["ga_"] / v["sa"], 4) if v["sa"] else None,
            "xsv_pct": round(1 - v["xga_"] / v["sa"], 4) if v["sa"] else None,
            "gsax60": per60(v["xga_"] - v["ga_"], v["toi_all"])}


def write(path, obj):
    path.write_text(json.dumps(obj, separators=(",", ":")))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", type=int, default=current_season())
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--no-fetch", action="store_true")
    a = ap.parse_args()
    build(a.season, a.out, not a.no_fetch)


if __name__ == "__main__":
    main()
