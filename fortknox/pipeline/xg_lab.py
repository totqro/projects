#!/usr/bin/env python3
"""
Try changes to the xG model the way the served model is actually used.

    python xg_lab.py                      every variant below
    python xg_lab.py base strength_cal    just these
    python xg_lab.py --list

The served model trains on every complete season but the last, stops and
calibrates on the last, and then scores a season it has never seen. So each
variant is scored walk-forward the same way: season S by a model trained on
2015 .. S-2 and calibrated on S-1, for S = 2023, 2024, 2025 and the games of
the season in progress. Nothing here is tuned on the season it is scored on.

For each variant and season: AUC and log loss over all unblocked shots, log
loss at 5v5 and on the power play alone, and xG / goals overall, at 5v5 and
on the power play (1.000 is perfect; the site's 5v5 and PP rates inherit any
miss). The last line of a variant pools the seasons and adds `team r`: across
every team-season, how well 5v5 xG share over a team's first half of the
schedule tracks its 5v5 goal share over the second half, which is what the
numbers are for. Log loss is the measure to choose by; AUC is swayed by
empty-net and long-range shots, and team r moves slowly (96 team-seasons).

Boosters are slow to fit and most variants share one, so each booster's raw
scores are kept in cache/lab/ and reused; delete that folder after changing
src/data/nhl_events.py or rebuilding the dataset.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import log_loss, roc_auc_score

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from src.models.nhl_xg import FEATURE_SETS, XGModel, strength_group  # noqa: E402

DATA = ROOT / "data" / "nhl_shots.parquet"
LAB = ROOT / "cache" / "lab"
TEST_SEASONS = (2023, 2024, 2025, 2026)

FULL_NUM, FULL_CAT = FEATURE_SETS["full"]

# name: (what it tries, numeric features, categorical features, booster
# params, calibration, extra-column builder or None). A params key "split"
# fits a separate booster for each strength group instead of one for all.
VARIANTS = {
    "base": ("the served recipe (RECENCY_DECAY): one isotonic curve for every shot",
             FULL_NUM, FULL_CAT, {}, "global", None),
    "strength_cal": ("same booster, a calibration curve each for 5v5, power play and the rest",
                     FULL_NUM, FULL_CAT, {}, "strength", None),
    "slow": ("learning rate 0.03, 63 leaves, min leaf 100",
             FULL_NUM, FULL_CAT, {"learning_rate": 0.03, "max_leaf_nodes": 63, "min_samples_leaf": 100},
             "strength", None),
    "small": ("15 leaves, min leaf 400: a smoother model",
              FULL_NUM, FULL_CAT, {"max_leaf_nodes": 15, "min_samples_leaf": 400}, "strength", None),
    "split": ("a separate booster each for 5v5, power play and the rest",
              FULL_NUM, FULL_CAT, {"split": True}, "strength", None),
    "rink": ("shot distance corrected for each rink's scorer (visiting-team shots, prior season)",
             FULL_NUM + ["distance_rink", "rink_shift"], FULL_CAT, {}, "strength", "rink"),
    "since2017": ("served booster trained on 2017 onward only (drops the low-scoring 2015-16)",
                  FULL_NUM, FULL_CAT, {"since": 2017, "decay": 0.6}, "global", None),
    "since2019": ("served booster trained on 2019 onward only",
                  FULL_NUM, FULL_CAT, {"since": 2019, "decay": 0.6}, "global", None),
    "decay0.4": ("served recipe with recency decay 0.4 instead of 0.6",
                 FULL_NUM, FULL_CAT, {"decay": 0.4}, "global", None),
    "last2": ("trained on the 2 seasons before the calibration season only (2023-24 for 2026)",
              FULL_NUM, FULL_CAT, {"window": 2, "decay": 0.6}, "global", None),
    "last3": ("trained on the 3 seasons before the calibration season only (2022-24 for 2026)",
              FULL_NUM, FULL_CAT, {"window": 3, "decay": 0.6}, "global", None),
    "decay0.2": ("served recipe with recency decay 0.2 instead of 0.6",
                 FULL_NUM, FULL_CAT, {"decay": 0.2}, "global", None),
    "decay0.8": ("served recipe with recency decay 0.8 instead of 0.6",
                 FULL_NUM, FULL_CAT, {"decay": 0.8}, "global", None),
    "context": ("plus last faceoff's zone, seconds since the strength changed, shots in the last 10 s",
                FULL_NUM + ["secs_since_strength_change", "team_shots_last10", "fwd_on_ice", "def_fwd_on_ice"],
                FULL_CAT + ["last_faceoff_zone"], {}, "strength", "context"),
}

# Recency grid: g<decay>_w<window> trains on the last `window` seasons before
# the calibration season ("all" = from 2015), each weighted `decay` times the
# one after it. One season (w1) has nothing to decay. The decay is always
# given, so these stay put when RECENCY_DECAY changes; base and the feature
# variants above use the served RECENCY_DECAY.
VARIANTS["g_w1"] = ("one season: the one before the calibration season", FULL_NUM, FULL_CAT,
                    {"window": 1}, "global", None)
for _d in (0.1, 0.2, 0.3, 0.4, 0.6):
    for _w in (2, 3, 4, None):
        _p = {k: v for k, v in (("decay", _d), ("window", _w)) if v is not None}
        VARIANTS[f"g{_d}_w{_w or 'all'}"] = (
            f"decay {_d}, {f'last {_w} seasons' if _w else 'every season'}",
            FULL_NUM, FULL_CAT, _p, "global", None)


# ----------------------------------------------------------------- features

def add_rink(df):
    """Each rink's scorer puts shots a little nearer or farther than the
    others do. Visiting teams are close to a random sample of the league, so
    the gap between how far out visitors' 5v5 shots are logged in a rink and
    how far out visitors' shots are logged everywhere is the scorer's bias.
    The correction for season S uses season S-1's gap for that home team (a
    rink's scorer mostly carries over), so nothing is taken from the season
    being scored. `rink_shift` is that gap in feet; `distance_rink` is the
    distance with it removed."""
    ev = df[(df.situation == "EV_5v5") & (df.is_home == 0) & (df.distance < 70)]
    league = ev.groupby("season").distance.mean()
    rink = ev.groupby(["season", "home_team"]).distance.mean()
    gap = (rink - league.reindex(rink.index.get_level_values(0)).to_numpy()).rename("rink_shift").reset_index()
    gap["season"] += 1
    out = df.merge(gap, on=["season", "home_team"], how="left")
    out["rink_shift"] = out.rink_shift.fillna(0.0)
    out["distance_rink"] = out.distance - out.rink_shift
    out.index = df.index
    return out


def add_context(df):
    """Columns the play-by-play supports that the model doesn't have yet;
    built by build_nhl_dataset.py once src/data/nhl_events.py carries them."""
    missing = [c for c in ("secs_since_strength_change", "team_shots_last10", "last_faceoff_zone",
                           "fwd_on_ice", "def_fwd_on_ice") if c not in df.columns]
    if missing:
        raise SystemExit(f"dataset has no {missing}: rebuild it with build_nhl_dataset.py")
    return df


BUILDERS = {"rink": add_rink, "context": add_context}


# ------------------------------------------------------------------ scoring

def booster_key(num, cat, params, builder, season):
    blob = json.dumps([sorted(num), sorted(cat), sorted(params.items()), builder, season,
                       DATA.stat().st_mtime_ns])
    return hashlib.sha1(blob.encode()).hexdigest()[:16]


def raw_scores(df, num, cat, params, builder, season):
    """(raw scores on the calibration season, raw scores on the test season,
    trees), fitted once and cached."""
    LAB.mkdir(parents=True, exist_ok=True)
    path = LAB / f"{booster_key(num, cat, params, builder, season)}.npz"
    valid, test = df[df.season == season - 1], df[df.season == season]
    if path.exists():
        z = np.load(path)
        return z["valid"], z["test"], int(z["trees"])
    params = dict(params)
    since = params.pop("since", None)
    if "window" in params:                # a rolling window: the last N seasons before calibration
        since = season - 1 - params.pop("window")
    fit_kw = {"decay": params.pop("decay")} if "decay" in params else {}
    train = df[(df.season <= season - 2) & (df.season >= (since or 0))]
    if not params.pop("split", False):
        m = XGModel(num, cat, **params).fit(train, valid, calibration=None, **fit_kw)
        rv, rt, trees = m.raw(valid), m.raw(test), m.clf.max_iter
    else:
        rv, rt, trees = np.zeros(len(valid)), np.zeros(len(test)), 0
        g_tr, g_v, g_te = (strength_group(x.situation) for x in (train, valid, test))
        for g in np.unique(g_tr):
            m = XGModel(num, cat, **params).fit(train[g_tr == g], valid[g_v == g], calibration=None)
            rv[g_v == g], rt[g_te == g] = m.raw(valid[g_v == g]), m.raw(test[g_te == g])
            trees += m.clf.max_iter
    np.savez(path, valid=rv, test=rt, trees=trees)
    return rv, rt, trees


def team_r(test, p):
    """Correlation, over every team-season, of first-half 5v5 xG share with
    second-half 5v5 goal share (regular season)."""
    t = test.assign(xg=p)
    t = t[(t.situation == "EV_5v5") & (t.is_playoff == 0)]
    rows = []
    for (season, team), _ in t.groupby(["season", "team"]):
        g = t[(t.season == season) & ((t.home_team == team) | (t.away_team == team))]
        ids = np.sort(g.game_id.unique())
        first = g.game_id.isin(ids[:len(ids) // 2])
        mine = g.team == team
        a, b = g[first], g[~first]
        rows.append((a.xg[mine[first]].sum() / a.xg.sum(), b.goal[mine[~first]].sum() / b.goal.sum(),
                     a.goal[mine[first]].sum() / a.goal.sum()))
    r = pd.DataFrame(rows, columns=["xg", "later", "goals"])
    return r.xg.corr(r.later), r.goals.corr(r.later)


def report(name, y, p, sit):
    ev, pp = (sit == "EV_5v5").to_numpy(), sit.str.startswith("PP").to_numpy()
    y = y.to_numpy()
    return (f"  {name:<8} AUC {roc_auc_score(y, p):.4f}  ll {log_loss(y, p, labels=[0, 1]):.5f}"
            f"  ll 5v5 {log_loss(y[ev], p[ev], labels=[0, 1]):.5f}"
            f"  ll PP {log_loss(y[pp], p[pp], labels=[0, 1]):.5f}"
            f"  xG/goals all {p.sum() / y.sum():.3f}  5v5 {p[ev].sum() / y[ev].sum():.3f}"
            f"  PP {p[pp].sum() / y[pp].sum():.3f}")


def run(df, name, seasons=TEST_SEASONS):
    what, num, cat, params, calibration, builder = VARIANTS[name]
    d = BUILDERS[builder](df) if builder else df
    print(f"\n[{name}] {what}")
    ys, ps, sits, tests = [], [], [], []
    for season in seasons:
        valid, test = d[d.season == season - 1], d[d.season == season]
        if not len(test):
            continue
        rv, rt, trees = raw_scores(d, num, cat, params, builder, season)
        cal = XGModel.fit_calibration(rv, valid.goal.to_numpy(), strength_group(valid.situation), calibration)
        p = XGModel.apply_calibration(cal, rt, strength_group(test.situation))
        print(report(str(season), test.goal, p, test.situation) + f"  ({trees} trees)", flush=True)
        ys.append(test.goal), ps.append(p), sits.append(test.situation)
        if season < TEST_SEASONS[-1]:      # complete seasons only, for the team check
            tests.append(test.assign(_p=p))
    if len(ys) < 2:
        return
    team = ""
    if tests:
        full = pd.concat(tests)
        rx, rg = team_r(full, full._p.to_numpy())
        team = f"  team r {rx:.3f} (goal share alone {rg:.3f})"
    print(report("pooled", pd.concat(ys), np.concatenate(ps), pd.concat(sits)) + team)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("variants", nargs="*", help="default: all")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--seasons", type=lambda v: [int(x) for x in v.split(",")], default=list(TEST_SEASONS),
                    help="comma-separated test seasons to score (default: all four)")
    a = ap.parse_args()
    if a.list:
        for k, v in VARIANTS.items():
            print(f"{k:<14}{v[0]}")
        return
    df = pd.read_parquet(DATA)
    df = df[df.event != "BLOCK"].reset_index(drop=True)
    for name in a.variants or list(VARIANTS):
        run(df, name, a.seasons)


if __name__ == "__main__":
    main()
