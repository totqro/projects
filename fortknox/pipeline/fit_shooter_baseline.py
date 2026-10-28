#!/usr/bin/env python3
"""Fit each shooter's finishing baseline: the goals above expected (GAx) per
unblocked shot his history says to expect, so Vs. Expected stops calling an
elite finisher's usual season "running hot".

The model's xG is an average shooter's chance. Some players beat it year
after year, but one season's GAx is mostly noise: on n shots worth p each,
goals vary by sum p(1 - p). So a career rate is shrunk toward the league's
(zero), by how much of its spread chance alone explains:

  baseline = (G - xG) / n  x  tau^2 / (tau^2 + noise)

where tau^2 is the spread of real finishing talent between shooters (fitted
here by the method of moments: the spread of season rates minus their
average noise), and noise is the variance of his own career rate. Seasons
count less the older they are (DECAY per season, chosen here by testing).

The test: for every season from 2018 on, baselines built only from the
seasons before it predict each shooter's GAx that season. Their squared
error is set against assuming zero, the page's call until now. A baseline
that doesn't beat zero isn't written.

  python fit_shooter_baseline.py          reads data/nhl_shots.parquet
                                          (build_nhl_dataset.py), writes
                                          data/shooter_baseline.json

Regular season only, unblocked shots, empty-net shots left out (no goalie
to beat). The baseline for season S uses seasons before S only.
"""
import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
SHOTS = ROOT / "data" / "nhl_shots.parquet"
MODEL = ROOT / "data" / "nhl_xg_model.joblib"
OUT = ROOT / "data" / "shooter_baseline.json"
TABLE = ROOT / "cache" / "shooter_seasons.parquet"

MIN_TEST = 50          # shots in the season, to be scored in the test
DECAYS = [1.0, 0.85, 0.7, 0.55]


def shooter_seasons(rebuild):
    """Per shooter and season: shots n, goals g, xG x, and v = sum p(1 - p)."""
    if TABLE.exists() and not rebuild:
        return pd.read_parquet(TABLE)
    df = pd.read_parquet(SHOTS)
    df = df[(df.event != "BLOCK") & (df.is_playoff == 0) & (df.situation != "EN_AGAINST") & df.shooter_id.notna()]
    model = joblib.load(MODEL)
    df = df.assign(xg=model.predict(df))
    df["v"] = df.xg * (1 - df.xg)
    t = (df.groupby(["shooter_id", "season"])
           .agg(n=("xg", "size"), g=("goal", "sum"), x=("xg", "sum"), v=("v", "sum"), pos=("shooter_position", "first"))
           .reset_index())
    t["shooter_id"] = t.shooter_id.astype(int)
    TABLE.parent.mkdir(exist_ok=True)
    t.to_parquet(TABLE, index=False)
    return t


def talent_variance(t, seasons):
    """tau^2: the spread of season GAx-per-shot rates beyond what chance gives."""
    s = t[t.season.isin(seasons) & (t.n >= 100)]
    r = (s.g - s.x) / s.n
    noise = s.v / s.n ** 2
    return max(float(r.var() - noise.mean()), 1e-7)


def baselines(t, season, decay, tau2):
    """Shrunk GAx per shot for every shooter with seasons before `season`."""
    p = t[t.season < season]
    w = decay ** (season - 1 - p.season)
    agg = pd.DataFrame({"id": p.shooter_id, "n": w * p.n, "gax": w * (p.g - p.x), "v": w ** 2 * p.v, "raw_n": p.n})
    agg = agg.groupby("id").sum()
    rate = agg.gax / agg.n
    noise = agg.v / agg.n ** 2
    agg["rate"] = rate * tau2 / (tau2 + noise)
    agg["shrink"] = tau2 / (tau2 + noise)
    return agg


def test(t, decay, first=2018):
    """Squared error of predicted season GAx, and of zero, over every test season."""
    rows = []
    for s in sorted(t.season.unique()):
        if s < first:
            continue
        tau2 = talent_variance(t, [y for y in t.season.unique() if y < s])
        b = baselines(t, s, decay, tau2).rate
        cur = t[(t.season == s) & (t.n >= MIN_TEST)].copy()
        cur["pred"] = cur.shooter_id.map(b).fillna(0) * cur.n
        cur["gax"] = cur.g - cur.x
        rows.append(cur.assign(test=s))
    r = pd.concat(rows)
    se, se0 = ((r.gax - r.pred) ** 2).sum(), (r.gax ** 2).sum()
    return r, se, se0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rebuild", action="store_true", help="rescore the shots instead of using the cached table")
    a = ap.parse_args()
    t = shooter_seasons(a.rebuild)
    print(f"{len(t):,} shooter-seasons, {t.season.min()}-{t.season.max()}, {int(t.n.sum()):,} shots")

    # Year-to-year: how much of one season's finishing carries to the next.
    nxt = t.merge(t.assign(season=t.season - 1), on=["shooter_id", "season"], suffixes=("", "_next"))
    nxt = nxt[(nxt.n >= 100) & (nxt.n_next >= 100)]
    print(f"season-to-season r of GAx/shot (100+ shots both): "
          f"{np.corrcoef((nxt.g - nxt.x) / nxt.n, (nxt.g_next - nxt.x_next) / nxt.n_next)[0, 1]:.3f} ({len(nxt)} pairs)")

    best = None
    for d in DECAYS:
        r, se, se0 = test(t, d)
        gain = 1 - se / se0
        corr = np.corrcoef(r.pred, r.g - r.x)[0, 1]
        print(f"decay {d:.2f}: error {se:,.0f} vs zero {se0:,.0f} -> {gain:+.1%}, r(pred, GAx) {corr:.3f}, "
              f"{len(r):,} shooter-seasons {r.test.min()}-{r.test.max()}")
        if best is None or se < best[1]:
            best = (d, se, se0, r)
    d, se, se0, r = best
    if se >= se0:
        print("No decay beats zero: nothing written.")
        return

    # Per test season, so a good average can't hide a bad year.
    for s, part in r.groupby("test"):
        e, e0 = ((part.g - part.x - part.pred) ** 2).sum(), ((part.g - part.x) ** 2).sum()
        print(f"  {s}: {1 - e / e0:+.1%} on {len(part)} shooters")
    # The elite finishers: did the baseline keep calling them hot?
    top = r[r.pred > 3]
    print(f"  shooters the baseline expected 3+ GAx from: {len(top)}, mean GAx {(top.g - top.x).mean():+.1f}, "
          f"mean predicted {top.pred.mean():+.1f}")

    seasons = sorted(int(s) for s in t.season.unique())
    out = {"about": "Finishing baseline per shooter: expected goals above expected per unblocked shot, from the "
                    "seasons before each target season, shrunk toward zero. fit_shooter_baseline.py.",
           "decay": d, "test_gain": round(1 - se / se0, 4), "seasons": {}}
    # The seasons the site publishes: the one in progress and the one before.
    for s in [y for y in seasons if y >= seasons[-1] - 1]:
        tau2 = talent_variance(t, [y for y in seasons if y < s])
        b = baselines(t, s, d, tau2)
        b = b[b.raw_n >= 20]
        out["seasons"][str(s)] = {"tau2": round(tau2, 8),
                                  "rate": {str(int(i)): round(float(v), 5) for i, v in b.rate.items() if abs(v) >= 1e-5}}
        print(f"baseline for {s}: {len(out['seasons'][str(s)]['rate'])} shooters, tau {tau2 ** 0.5:.4f} GAx/shot")
    OUT.write_text(json.dumps(out, separators=(",", ":")) + "\n")
    print(f"-> {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
