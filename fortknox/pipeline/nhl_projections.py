"""
Projected standings and playoff odds for the season in progress.

Plays out the rest of the regular season 10,000 times (projections.py) from
the published game index and writes <sheets>/<season>/projections.json for
the Playoff odds page. Completed games are the ones in the index, so the
projection always matches the standings the site shows; every other game on
the NHL schedule is simulated.

Elo starts from the seed in data/projection_model.json (fit_projections.py)
and replays each published season after it from its index.json.

    .venv/bin/python nhl_projections.py --sheets ../data
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import projections as P
from nhl_sheets import current_season

HERE = Path(__file__).resolve().parent
MODEL = HERE / "data" / "projection_model.json"
SCHEDULE = "https://api-web.nhle.com/v1/club-schedule-season/{}/{}{}"


def get(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "highslot-projections/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if i == tries - 1:
                raise
            time.sleep(2 ** i)


def index_games(sheets: Path, season: int):
    """The season's regular-season games from the published index, in order."""
    idx = json.loads((sheets / str(season) / "index.json").read_text())
    games = [{"id": g["id"], "date": g["date"], "home": g["home"], "away": g["away"], "hs": g["hs"], "as": g["as"],
              "end": g["end"], "hx5": g.get("hxg5"), "ax5": g.get("axg5")}
             for g in idx["games"] if g["type"] == 2]
    return sorted(games, key=lambda g: (g["date"], g["id"])), idx.get("updated")


def schedule(teams, season: int):
    """Every regular-season game on the season's schedule, by id."""
    out = {}
    for t in teams:
        for g in get(SCHEDULE.format(t, season, season + 1))["games"]:
            if g["gameType"] == 2:
                out[g["id"]] = {"id": g["id"], "date": g["gameDate"],
                                "home": g["homeTeam"]["abbrev"], "away": g["awayTeam"]["abbrev"]}
        time.sleep(0.2)
    return out


def run(sheets: Path, season: int, sims: int):
    model = json.loads(MODEL.read_text())
    align = P.alignment(season)

    # Elo: the seed, then every published season after it, this one last.
    seed = model["elo_seed"]
    elo = P.Elo(seed["ratings"], seed["season"])
    published = json.loads((sheets / "seasons.json").read_text())["seasons"]
    for s in range(seed["season"] + 1, season):
        if s not in published:
            print(f"warning: season {s} is not published; Elo skips it", file=sys.stderr)
            continue
        for g in index_games(sheets, s)[0]:
            elo.update(g["home"], g["away"], g["hs"] > g["as"], s)
    played, updated = index_games(sheets, season)
    tallies = {}
    for g in played:
        elo.update(g["home"], g["away"], g["hs"] > g["as"], season)
        P.record_game(tallies, g)

    sched = schedule(sorted(align), season)
    done = {g["id"] for g in played}
    remaining = sorted((g for g in sched.values() if g["id"] not in done), key=lambda g: (g["date"], g["id"]))
    unknown = {t for g in remaining for t in (g["home"], g["away"])} - set(align)
    if unknown:
        raise SystemExit(f"teams on the schedule with no division: {sorted(unknown)}")
    dates = defaultdict(set)
    for g in list(sched.values()) + played:
        dates[g["home"]].add(g["date"])
        dates[g["away"]].add(g["date"])

    ratings = elo.snapshot(season)
    teams, res = P.simulate(model, align, tallies, remaining, ratings, n=sims, seed=season, dates_by_team=dates)
    rows = P.summarize(teams, res, align, tallies)
    for r in rows:
        t = tallies.get(r["team"], P.Tally())
        r["elo"] = round(ratings.get(r["team"], P.INITIAL_ELO), 1)
        r["xgd"] = round(t.xgd, 3)
        r["left"] = sum(r["team"] in (g["home"], g["away"]) for g in remaining)
    rows.sort(key=lambda r: (-r["proj"], -r["playoff"], r["team"]))

    out = {
        "season": season,
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "index_updated": updated,
        "as_of": played[-1]["date"] if played else None,
        "sims": sims, "games_played": len(played), "games_left": len(remaining),
        "model": {"version": model["version"], "sigma": model["sigma"], "min_gp": model["min_gp"],
                  "core": model["core"], "early": model["early"], "ot": model["ot"]},
        "teams": rows,
    }
    path = sheets / str(season) / "projections.json"
    path.write_text(json.dumps(out, separators=(",", ":")) + "\n")
    print(f"projections: {len(played)} played, {len(remaining)} simulated x {sims} -> {path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sheets", type=Path, required=True, help="the published sheets folder (seasons.json, <season>/index.json)")
    ap.add_argument("--season", type=int, default=None)
    ap.add_argument("--sims", type=int, default=10000)
    a = ap.parse_args()
    run(a.sheets, a.season or current_season(), a.sims)


if __name__ == "__main__":
    main()
