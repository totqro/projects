#!/usr/bin/env python3
"""
How many features do we actually need?

    python ablate_features.py

Trains nested feature tiers, smallest to largest, on both a linear model
(logistic regression) and a tree model (histogram gradient boosting), timing
every fit. Reports AUC, log loss, and mean per-situation calibration error --
the last one because global metrics demonstrably hide situation-level bias in
this dataset.

The point is to find where accuracy stops paying for training time, rather
than assuming more features are better.
"""

import sys, time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))
from src.data.schema import assert_no_holdout_leak, FEATURE_COLUMNS, CATEGORICAL_FEATURES

VALID_SEASON, TEST_SEASON = 2024, 2025

# Nested tiers: each adds to the one before, so the marginal value of each
# group is visible. Ordered by how fundamental the information is.
TIERS = {
    "1 geometry":   ["distance", "angle_from_net"],
    "2 +shot":      ["shot_type", "is_rebound"],
    "3 +strength":  ["situation"],
    "4 +location":  ["x_adj", "y_abs", "is_behind_net", "off_wing", "shooter_hand"],
    "5 +sequence":  ["prev_event", "prev_event_zone", "time_since_last_event",
                     "distance_from_last_event", "speed_from_last_event"],
    "6 +gamestate": ["score_differential", "period_format", "is_home", "is_playoff",
                     "time_seconds", "is_empty_net", "shooter_net_empty"],
    "7 all":        None,   # every feature in the schema
}


def make_model(kind, cats, nums):
    if kind == "logistic":
        return Pipeline([
            ("prep", ColumnTransformer([
                ("num", StandardScaler(), nums),
                ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=30), cats),
            ])),
            ("clf", LogisticRegression(max_iter=2000)),
        ])
    # Trees take categoricals natively — ordinal-encode, don't one-hot.
    return Pipeline([
        ("prep", ColumnTransformer([
            ("num", "passthrough", nums),
            ("cat", OrdinalEncoder(handle_unknown="use_encoded_value",
                                   unknown_value=-1), cats),
        ])),
        ("clf", HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.1, early_stopping=True,
            categorical_features=list(range(len(nums), len(nums) + len(cats))),
            random_state=0)),
    ])


def situation_cal_error(part, p):
    """Mean |predicted/actual - 1| across situations with enough shots."""
    t = part.assign(_p=p)
    errs = []
    for _, g in t.groupby("situation"):
        if len(g) >= 300 and g.goal.sum() > 0:
            errs.append(abs(g._p.sum() / g.goal.sum() - 1))
    return float(np.mean(errs))


def main():
    df = pd.read_parquet(Path(__file__).resolve().parent / "data" / "shots.parquet")
    train = df[df.season < VALID_SEASON]
    assert_no_holdout_leak(train)
    test = df[df.season == TEST_SEASON]
    print(f"train {len(train):,} shots (<{VALID_SEASON})   test {len(test):,} ({TEST_SEASON})\n")

    feats: list[str] = []
    rows = []
    for tier, add in TIERS.items():
        feats = list(FEATURE_COLUMNS) if add is None else feats + add
        cats = [c for c in feats if c in CATEGORICAL_FEATURES]
        nums = [c for c in feats if c not in CATEGORICAL_FEATURES]

        for kind in ("logistic", "tree"):
            model = make_model(kind, cats, nums)
            t0 = time.perf_counter()
            model.fit(train[feats], train.goal)
            fit_s = time.perf_counter() - t0

            p = model.predict_proba(test[feats])[:, 1]
            rows.append({
                "tier": tier, "model": kind, "n_feat": len(feats),
                "fit_s": round(fit_s, 1),
                "auc": round(roc_auc_score(test.goal, p), 4),
                "log_loss": round(log_loss(test.goal, p, labels=[0, 1]), 5),
                "cal_err": round(situation_cal_error(test, p), 4),
            })
            print(f"  {tier:<13} {kind:<9} {len(feats):>2} feats  "
                  f"{fit_s:>6.1f}s  AUC {rows[-1]['auc']:.4f}  "
                  f"cal_err {rows[-1]['cal_err']:.4f}")

    res = pd.DataFrame(rows)
    print("\n" + "=" * 78)
    for kind in ("logistic", "tree"):
        sub = res[res.model == kind].reset_index(drop=True)
        sub["d_auc"] = sub.auc.diff().fillna(0).round(4)
        print(f"\n{kind.upper()}")
        print(sub[["tier", "n_feat", "fit_s", "auc", "d_auc", "log_loss",
                   "cal_err"]].to_string(index=False))

    mp = test.mp_xg.clip(1e-6, 1 - 1e-6)
    print(f"\nMoneyPuck benchmark on the same rows: "
          f"AUC {roc_auc_score(test.goal, mp):.4f}  "
          f"log_loss {log_loss(test.goal, mp, labels=[0,1]):.5f}  "
          f"cal_err {situation_cal_error(test, mp.to_numpy()):.4f}")
    res.to_csv("data/ablation.csv", index=False)


if __name__ == "__main__":
    main()
