#!/usr/bin/env python3
"""
The full-data xG model, trained on the NHL's own feed.

    python train_nhl_xg.py                 evaluate (the protocol below)
    python train_nhl_xg.py --production    refit on everything and save

xg_model.py is the five-feature model a person can tag from the stands. This
one is for games nobody tagged: it uses every column the public play-by-play
and shift chart support (see src/data/nhl_events.py), and it is trained on
the same feed the nightly job scores, so there is no gap between the data it
learned from and the data it sees.

Protocol
    train   2015-16 .. 2022-23
    valid   2023-24        early stopping and every modelling choice
    test    2024-25, 2025-26 (schema.HOLDOUT_SEASONS), plus the 2026-27
            games played so far: looked at once, reported, never tuned on

Two feature sets are fitted on the same rows so the gain is visible:
    mp      the columns MoneyPuck's file also has
    full    mp + sequence (rush and lateral proxies, rebound source),
            shift fatigue, shooter age and height
Unblocked shots only (goals, saves, misses), like MoneyPuck, so the two are
compared on the same footing. Seasons are weighted toward the most recent and
the model is recalibrated on the validation season; src/models/nhl_xg.py has
the measurements behind that.

--production is a different thing on purpose. Shot logging drifts every
season, so the model that scores tonight's games has to see the latest ones:
it trains on every complete season but the last, stops and calibrates on the
last, and is what nhl_sheets.py loads. It does train on HOLDOUT_SEASONS, so
its numbers are not evaluation numbers; the honest ones come from the default
run, and the season in progress is the production model's own fresh test.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import log_loss, roc_auc_score

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from src.data.schema import HOLDOUT_SEASONS, assert_no_holdout_leak  # noqa: E402
from src.models.nhl_xg import FEATURE_SETS, XGModel  # noqa: E402

DATA = ROOT / "data" / "nhl_shots.parquet"
MODEL_PATH = ROOT / "data" / "nhl_xg_model.joblib"
TRAIN_LAST, VALID = 2022, 2023
TEST = sorted(HOLDOUT_SEASONS)

def headline(name, y, p):
    return (f"  {name:<28} AUC {roc_auc_score(y, p):.4f}   log loss {log_loss(y, p, labels=[0, 1]):.5f}"
            f"   xG/goals {p.sum() / y.sum():.4f}   n {len(y):,}")


def by_situation(df, p):
    t = df.assign(_p=p)
    out = []
    for sit, g in t.groupby("situation"):
        if len(g) >= 300 and g.goal.sum():
            out.append((sit, len(g), int(g.goal.sum()), g._p.sum() / g.goal.sum()))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--production", action="store_true",
                    help="refit on every complete season and save the served model")
    a = ap.parse_args()

    df = pd.read_parquet(DATA)
    df = df[df.event != "BLOCK"].reset_index(drop=True)
    if a.production:
        return production(df)
    train = df[df.season <= TRAIN_LAST]
    valid = df[df.season == VALID]
    tests = {s: df[df.season == s] for s in TEST + [max(df.season)] if s > VALID}
    assert_no_holdout_leak(train)
    assert VALID not in set(train.season)
    print(f"train {train.season.min()}-{TRAIN_LAST} {len(train):,}   valid {VALID} {len(valid):,}   "
          + "   ".join(f"test {s} {len(t):,}" for s, t in tests.items()))

    models, results = {}, {}
    for name, (num, cat) in FEATURE_SETS.items():
        m = XGModel(num, cat).fit(train, valid)
        models[name] = m
        print(f"\n[{name}] {len(num) + len(cat)} features, {m.clf.max_iter} trees")
        for s, part in [(VALID, valid)] + list(tests.items()):
            p = m.predict(part)
            results[(name, s)] = p
            print(headline(f"{name} {s}", part.goal, p))

    print("\nAgainst MoneyPuck, on the shots both have")
    for s, part in [(VALID, valid)] + list(tests.items()):
        mask = part.mp_xg.notna().to_numpy()
        if mask.sum() < 1000:
            continue
        y = part.goal[mask]
        print(headline(f"moneypuck {s}", y, part.mp_xg[mask].clip(1e-6, 1 - 1e-6).to_numpy()))
        for name in models:
            print(headline(f"{name} {s}", y, results[(name, s)][mask]))

    test_all = pd.concat([tests[s] for s in TEST])
    p = models["full"].predict(test_all)
    print(f"\nfull model, calibration by situation on {TEST}")
    for sit, n, g, r in by_situation(test_all, p):
        print(f"    {sit:<22}{n:>8,}{g:>7,}  xG/goals {r:.3f}")

    print("\nfull model, calibration by predicted decile on the test seasons")
    q = pd.qcut(p, 10, duplicates="drop")
    t = pd.DataFrame({"y": test_all.goal.to_numpy(), "p": p, "q": q})
    for iv, g in t.groupby("q", observed=True):
        print(f"    {iv.left:.3f}-{iv.right:.3f}  n {len(g):>7,}  xG {g.p.mean():.4f}  "
              f"actual {g.y.mean():.4f}")

    print("\nfull model, xG/goals by season")
    for s_, part in [(VALID, valid)] + list(tests.items()):
        print(f"    {s_}  {results[('full', s_)].sum() / part.goal.sum():.4f}")


def production(df):
    """Train on every complete season but the last; stop and calibrate on the
    last; save. The season in progress (the max season) is left out of both."""
    import joblib
    in_progress = int(df.season.max())
    calib = in_progress - 1
    train, valid = df[df.season < calib], df[df.season == calib]
    num, cat = FEATURE_SETS["full"]
    m = XGModel(num, cat).fit(train, valid)
    print(f"production: train {train.season.min()}-{calib - 1} {len(train):,}, "
          f"calibrate {calib} {len(valid):,}, {m.clf.max_iter} trees")
    live = df[df.season == in_progress]
    if len(live):
        print(headline(f"season in progress {in_progress}", live.goal, m.predict(live)))
    joblib.dump(m, MODEL_PATH, compress=3)
    meta = {"features_numeric": m.numeric, "features_categorical": m.categorical,
            "trees": int(m.clf.max_iter), "train": [int(train.season.min()), calib - 1],
            "calibrated_on": calib}
    MODEL_PATH.with_suffix(".json").write_text(json.dumps(meta, indent=1))
    print(f"Saved {MODEL_PATH.name} ({MODEL_PATH.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
