#!/usr/bin/env python3
"""
Does recalibrating during the season fix a season that scores more (or less)
than the calibration season did?

The served model is calibrated once, on the last complete season, so a
season whose scoring level moves comes out off by the same amount all year
(2026-27 so far: xG/goals 0.97; 2025-26: 1.06). Each method here adjusts
the served model's probabilities using only the games played on earlier
dates of the same season, so nothing sees its own game:

  served          no adjustment (the decay-0.2 recipe, as served)
  ratio k         scale every shot's odds by (goals + k) / (xG + k) so far:
                  k is how many goals of evidence it takes to move halfway
  group k         the same, separately for 5v5, power play and the rest
                  (each group's k scaled by its share of goals)
  iso w           refit the isotonic curve weekly on the calibration season
                  plus the season so far, its shots weighted w times

Scored walk-forward like xg_lab.py (season S: booster trained to S-2,
calibrated on S-1) for 2023-2026, from xg_lab's cached boosters.

    python experiments/xg_inseason.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import log_loss

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.models.nhl_xg import XGModel, strength_group  # noqa: E402
from xg_lab import DATA, FULL_CAT, FULL_NUM, TEST_SEASONS, raw_scores  # noqa: E402

PARAMS = {"decay": 0.2}          # = g0.2_wall / decay0.2, the served recipe


def scale_odds(p, r):
    return p * r / (1 - p + p * r)


def so_far(dates, y, p, mask=None):
    """Goals and xG on dates strictly before each shot's date."""
    m = np.ones(len(y), bool) if mask is None else mask
    t = pd.DataFrame({"d": dates[m], "y": y[m], "p": p[m]}).groupby("d")[["y", "p"]].sum()
    cum = t.cumsum().shift(fill_value=0)
    idx = pd.Index(cum.index)
    pos = idx.searchsorted(dates, side="left")      # first date >= the shot's date
    G = np.r_[0, cum.y.to_numpy() + t.y.to_numpy()]  # totals through each date, 0 before the first
    X = np.r_[0, cum.p.to_numpy() + t.p.to_numpy()]
    return G[pos], X[pos]


def ratio(dates, y, p, k):
    G, X = so_far(dates, y, p)
    return scale_odds(p, (G + k) / (X + k))


def group_ratio(dates, y, p, grp, k):
    out = p.copy()
    for g in np.unique(grp):
        m = grp == g
        share = y[m].sum() / max(y.sum(), 1)
        kg = max(k * share, 10)
        G, X = so_far(dates[m], y[m], p[m])
        out[m] = scale_odds(p[m], (G + kg) / (X + kg))
    return out


def iso_weekly(dates, y, raw, raw_v, y_v, w):
    week = pd.to_datetime(pd.Series(dates)).dt.to_period("W").to_numpy()
    out = np.empty(len(y))
    for wk in np.unique(week):
        before = week < wk
        x = np.r_[raw_v, raw[before]]
        t = np.r_[y_v, y[before]]
        sw = np.r_[np.ones(len(raw_v)), np.full(before.sum(), w)]
        iso = IsotonicRegression(out_of_bounds="clip", y_min=1e-4, y_max=0.99).fit(x, t, sample_weight=sw)
        m = week == wk
        out[m] = iso.predict(raw[m])
    return out


def line(name, y, p, sit, late):
    ev, pp = sit == "EV_5v5", np.char.startswith(sit.astype(str), "PP")
    return (f"  {name:<11} ll {log_loss(y, p, labels=[0, 1]):.5f}  later half ll {log_loss(y[late], p[late], labels=[0, 1]):.5f}"
            f"  xG/goals all {p.sum() / y.sum():.3f}  later half {p[late].sum() / y[late].sum():.3f}"
            f"  5v5 {p[ev].sum() / y[ev].sum():.3f}  PP {p[pp].sum() / y[pp].sum():.3f}")


def main():
    df = pd.read_parquet(DATA)
    df = df[df.event != "BLOCK"].reset_index(drop=True)
    pooled = {}
    for season in TEST_SEASONS:
        valid, test = df[df.season == season - 1], df[df.season == season]
        rv, rt, _ = raw_scores(df, FULL_NUM, FULL_CAT, PARAMS, None, season)
        cal = XGModel.fit_calibration(rv, valid.goal.to_numpy(), strength_group(valid.situation), "global")
        base = XGModel.apply_calibration(cal, rt, strength_group(test.situation))
        y, dates = test.goal.to_numpy(), test.game_date.astype(str).to_numpy()
        sit, grp = test.situation.astype(str).to_numpy(), strength_group(test.situation)
        late = dates >= np.sort(np.unique(dates))[len(np.unique(dates)) // 2]
        methods = {"served": base}
        for k in (100, 300, 1000):
            methods[f"ratio {k}"] = ratio(dates, y, base, k)
        for k in (300, 1000):
            methods[f"group {k}"] = group_ratio(dates, y, base, grp, k)
        for w in (1, 3):
            methods[f"iso {w}"] = iso_weekly(dates, y, rt, rv, valid.goal.to_numpy(), w)
        print(f"\n{season}  ({test.game_id.nunique()} games, {int(y.sum())} goals, served xG/goals {base.sum() / y.sum():.3f})")
        for name, p in methods.items():
            print(line(name, y, p, sit, late), flush=True)
            pooled.setdefault(name, []).append((y, p, sit, late))
    print("\npooled")
    for name, parts in pooled.items():
        y, p, sit, late = (np.concatenate(x) for x in zip(*parts))
        print(line(name, y, p, sit, late))


if __name__ == "__main__":
    main()
