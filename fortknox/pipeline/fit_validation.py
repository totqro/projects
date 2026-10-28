#!/usr/bin/env python3
"""Which team numbers predict the rest of a season: the Model page's
predictive check.

For every regular season since 2015-16 and every team, take each number
over the team's first N games and see how well it predicts the team's
points % over the rest of that season (games N+1 on, at least MIN_REST of
them). The numbers:

  pts    points %                       (the standings)
  gs     goal share                     (shootout deciders left out)
  xgs    xG share, all situations       (empty-net shots left out)
  xgs5   xG share at 5-on-5
  dpts   deserved points %              (each game's expected points from
                                         its deserve-to-win, lib/deserve.ts:
                                         2 x P(win) + 1.5 x P(tie), a tie
                                         being an overtime coin flip)

"How well" is the correlation across teams, worked out per season and
averaged (Fisher z, weighted by teams). Writes ../app/model/validation.json,
which the Model page draws; it only changes when this is rerun.

  python fit_validation.py          reads data/nhl_shots.parquet
                                    (build_nhl_dataset.py) and the raw cache

The served model was trained on 2015-16 to 2024-25, so its xG on those
seasons is in-sample. It never sees which team took a shot, but the file
also keeps the most recent full season on its own.
"""
import gzip
import json
import sys
from collections import defaultdict
from multiprocessing import Pool
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
SHOTS = ROOT / "data" / "nhl_shots.parquet"
MODEL = ROOT / "data" / "nhl_xg_model.joblib"
CACHE = ROOT / "cache" / "nhl"
OUT = ROOT.parent / "app" / "model" / "validation.json"
TABLE = ROOT / "cache" / "team_games.parquet"

MAX_N = 60
MIN_REST = 10
KEYS = ["pts", "gs", "xgs", "xgs5", "dpts"]


def goal_chances(xgs):
    """P(0, 1, 2… goals) on shots each going in with its own probability."""
    d = np.ones(1)
    for p in xgs:
        d = np.append(d * (1 - p), 0) + np.append(0, d * p)
    return d


def expected_points(h, a):
    """Each side's expected points from its shots: 2 for a win, and a tie
    (overtime) worth 1.5 to each, a point plus half a coin flip."""
    H, A = goal_chances(h), goal_chances(a)
    j = np.outer(H, A)                       # j[i, k] = P(home i, away k)
    hw, aw, tie = np.tril(j, -1).sum(), np.triu(j, 1).sum(), np.trace(j)
    return 2 * hw + 1.5 * tie, 2 * aw + 1.5 * tie


def result(path):
    """Final score and how it ended, from a cached play-by-play."""
    with gzip.open(path, "rt") as f:
        p = json.load(f)
    if p.get("gameType") != 2:
        return None
    return (p["id"], p.get("gameDate"), p["homeTeam"]["abbrev"], p["awayTeam"]["abbrev"],
            p["homeTeam"].get("score", 0), p["awayTeam"].get("score", 0),
            (p.get("gameOutcome") or {}).get("lastPeriodType", "REG"))


def team_games(seasons):
    """One row per team per regular-season game, in date order."""
    if TABLE.exists():
        return pd.read_parquet(TABLE)
    files = [f for s in seasons for f in sorted((CACHE / str(s)).glob("*.pbp.json.gz"))]
    with Pool() as pool:
        res = [r for r in pool.map(result, files, chunksize=64) if r]
    games = pd.DataFrame(res, columns=["game_id", "date", "home", "away", "hs", "as_", "end"])

    df = pd.read_parquet(SHOTS)
    df = df[(df.event != "BLOCK") & (df.is_playoff == 0) & (df.situation != "EN_AGAINST")]
    df = df.assign(xg=joblib.load(MODEL).predict(df))
    by = {g: part for g, part in df.groupby("game_id")}

    rows = []
    for g in games.itertuples():
        sh = by.get(g.game_id)
        if sh is None:
            continue
        home = sh.team == g.home
        h, a = sh.xg[home].to_numpy(), sh.xg[~home].to_numpy()
        five = sh.situation == "EV_5v5"
        hp, ap = expected_points(h, a)
        so = g.end == "SO"
        # Shootout deciders aren't goals scored in play.
        hg, ag = g.hs - (so and g.hs > g.as_), g.as_ - (so and g.as_ > g.hs)
        for me, op, gf, ga, xf, xa, x5f, x5a, dp, won in (
                (g.home, g.away, hg, ag, h.sum(), a.sum(), sh.xg[home & five].sum(), sh.xg[~home & five].sum(), hp, g.hs > g.as_),
                (g.away, g.home, ag, hg, a.sum(), h.sum(), sh.xg[~home & five].sum(), sh.xg[home & five].sum(), ap, g.as_ > g.hs)):
            rows.append({"season": g.game_id // 1_000_000, "game_id": g.game_id, "date": g.date, "team": me,
                         "pts": 2 if won else (1 if g.end != "REG" else 0),
                         "gf": gf, "ga": ga, "xgf": xf, "xga": xa, "xgf5": x5f, "xga5": x5a, "dpts": dp})
    t = pd.DataFrame(rows).sort_values(["season", "team", "date", "game_id"])
    TABLE.parent.mkdir(exist_ok=True)
    t.to_parquet(TABLE, index=False)
    return t


def share(f, a):
    return f / (f + a) if f + a else 0.5


def predictors(first):
    """Each number over a team's first games."""
    s = first.sum(numeric_only=True)
    n = len(first)
    return {"pts": s.pts / (2 * n), "gs": share(s.gf, s.ga), "xgs": share(s.xgf, s.xga),
            "xgs5": share(s.xgf5, s.xga5), "dpts": s.dpts / (2 * n)}


def correlations(t, seasons):
    """r[key][N-1]: mean correlation with points % over the rest, across seasons."""
    out = {k: [] for k in KEYS}
    teams_at = []
    for n in range(1, MAX_N + 1):
        z, w = defaultdict(float), 0
        for s in seasons:
            xs, y = defaultdict(list), []
            for _, g in t[t.season == s].groupby("team"):
                if len(g) - n < MIN_REST:
                    continue
                p = predictors(g.iloc[:n])
                rest = g.iloc[n:]
                for k in KEYS:
                    xs[k].append(p[k])
                y.append(rest.pts.sum() / (2 * len(rest)))
            if len(y) < 10:
                continue
            for k in KEYS:
                z[k] += np.arctanh(np.corrcoef(xs[k], y)[0, 1]) * len(y)
            w += len(y)
        teams_at.append(w)
        for k in KEYS:
            out[k].append(round(float(np.tanh(z[k] / w)), 4) if w else None)
    return out, teams_at


def main():
    seasons = sorted(int(p.name) for p in CACHE.iterdir() if p.name.isdigit())
    t = team_games(seasons)
    # Full seasons only: the one in progress has no "rest" yet.
    full = sorted(s for s in t.season.unique() if t[t.season == s].groupby("team").size().min() >= 48)
    print(f"{len(t) // 2:,} games, full seasons {full[0]}-{full[-1]} ({len(full)})")
    allr, teams = correlations(t, full)
    last, _ = correlations(t, full[-1:])
    for n in (5, 10, 20, 30, 41, 60):
        print(f"  after {n:>2} games: " + "  ".join(f"{k} {allr[k][n - 1]:.3f}" for k in KEYS) + f"   ({teams[n - 1]} team-seasons)")
    out = {"about": "Correlation of each number over a team's first N games with its points % over the rest of the "
                    "season, averaged over seasons. pipeline/fit_validation.py.",
           "seasons": [int(s) for s in full], "min_rest": MIN_REST, "n": list(range(1, MAX_N + 1)),
           "teams": teams, "r": allr, "last": {"season": int(full[-1]), "r": last}}
    OUT.write_text(json.dumps(out, separators=(",", ":")) + "\n")
    print(f"-> {OUT.relative_to(ROOT.parent)}")


if __name__ == "__main__":
    main()
