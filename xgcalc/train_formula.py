#!/usr/bin/env python3
"""
The specified model, then Platt-calibrated.

    goal ~ distance + angle + shotType + shotRebound + shotRush + strength_state

    python train_formula.py

Three disjoint, time-ordered slices, the same protocol the win model's
calibration uses:

    train the model      2018-2023   666,342 shots
    fit the calibrator   2024        the model has never seen it
    score everything     2025        neither has seen it

Fitting the calibrator on 2024 does not violate the project's "never train on
2024" rule: `assert_no_holdout_leak` guards the MODEL's training set, and the
calibrator is a separate two-parameter map fit on the model's *outputs*. A
calibrator fit on the model's own training data would be fit to its
overconfidence and report fantasy numbers.

Note on shotRush: MoneyPuck's rush flag is the field this project found
unreliable (rate decays 0.25% -> 0.06% across seasons; see README data-quality
note 2). It is included here because it is part of the requested spec, and its
fitted coefficient is printed so its actual contribution is visible rather
than assumed.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.data.schema import (TEST_SEASON, VALIDATION_SEASON,
                             assert_no_holdout_leak)
from src.models.calibration import (choose_calibration, fit_calibrator,
                                    reliability_table, score)

# goal ~ distance + angle + shotType + shotRebound + shotRush + strength_state
NUMERIC = ["distance", "angle_from_net", "is_rebound", "is_rush_mp"]
CATEGORICAL = ["shot_type", "strength_state"]
FEATURES = NUMERIC + CATEGORICAL

CALIBRATOR_PATH = ROOT / "data" / "xg_calibrator.json"


def build():
    return Pipeline([
        ("prep", ColumnTransformer([
            ("num", StandardScaler(), NUMERIC),
            ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=30),
             CATEGORICAL),
        ])),
        ("clf", LogisticRegression(max_iter=2000)),
    ])


def main():
    df = pd.read_parquet(ROOT / "data" / "shots.parquet")
    train = df[df.season < VALIDATION_SEASON]
    calib = df[df.season == VALIDATION_SEASON]
    test = df[df.season == TEST_SEASON]
    assert_no_holdout_leak(train)

    print("goal ~ distance + angle + shotType + shotRebound + shotRush + strength_state\n")
    print(f"  train model      {train.season.min()}-{train.season.max()}  {len(train):>8,} shots")
    print(f"  fit calibrator   {VALIDATION_SEASON}       {len(calib):>8,} shots")
    print(f"  score            {TEST_SEASON}       {len(test):>8,} shots")

    model = build()
    model.fit(train[FEATURES], train.goal)

    p_calib = model.predict_proba(calib[FEATURES])[:, 1]
    p_test = model.predict_proba(test[FEATURES])[:, 1]
    y_calib, y_test = calib.goal, test.goal

    # --- calibrate ---------------------------------------------------------
    metrics, fitted = {}, {}
    for method in ("uncalibrated", "platt", "isotonic"):
        cal = fit_calibrator(method, p_calib, y_calib)
        pt = cal.predict(p_test)
        m = score(pt, y_test)
        m["auc"] = roc_auc_score(y_test, pt)
        metrics[method], fitted[method] = m, cal

    print(f"\nCalibration, scored on {TEST_SEASON}")
    print(f"  {'method':<15}{'log loss':>10}{'brier':>10}{'ECE':>9}"
          f"{'sum/goals':>11}{'AUC':>8}")
    for name, m in metrics.items():
        print(f"  {name:<15}{m['log_loss']:>10.5f}{m['brier']:>10.5f}"
              f"{m['ece']:>9.5f}{m['sum_ratio']:>11.4f}{m['auc']:>8.4f}")

    chosen, chosen_m = choose_calibration(metrics)
    base = metrics["uncalibrated"]
    print(f"\n  Gate: adopt only if a method beats raw on BOTH log loss and Brier.")
    for m_name in ("platt", "isotonic"):
        m = metrics[m_name]
        print(f"    {m_name:<10} log loss {'PASS' if m['log_loss'] < base['log_loss'] else 'fail'}"
              f"   brier {'PASS' if m['brier'] < base['brier'] else 'fail'}")
    print(f"  Verdict: {'adopt ' + chosen if chosen else 'ship RAW probabilities (no method cleared the gate)'}")

    # --- reliability -------------------------------------------------------
    # Binned by the RAW prediction, so every column describes the SAME shots.
    # (Binning raw and calibrated separately puts different shots in each row
    # and makes the comparison meaningless.)
    print(f"\n  Reliability on {TEST_SEASON}, binned by raw prediction")
    t = pd.DataFrame({
        "raw": p_test,
        "platt": fitted["platt"].predict(p_test),
        "isotonic": fitted["isotonic"].predict(p_test),
        "y": y_test.to_numpy(),
    })
    bins = pd.cut(t.raw, [0, .1, .2, .3, .4, .5, .6, .7, .8, 1.0])
    g = t.groupby(bins, observed=True).agg(
        n=("y", "size"), raw=("raw", "mean"), platt=("platt", "mean"),
        isotonic=("isotonic", "mean"), actual=("y", "mean"))
    print(f"    {'bin':<14}{'n':>8}{'raw':>9}{'platt':>9}{'isotonic':>10}{'actual':>9}")
    for interval, r in g.iterrows():
        print(f"    {str(interval):<14}{int(r.n):>8,}{r.raw:>9.4f}"
              f"{r.platt:>9.4f}{r.isotonic:>10.4f}{r.actual:>9.4f}")

    # --- what the spec's terms are worth -----------------------------------
    names = model.named_steps["prep"].get_feature_names_out()
    coefs = model.named_steps["clf"].coef_[0]
    print("\n  Fitted coefficients (log-odds)")
    for n, c in sorted(zip(names, coefs), key=lambda r: -abs(r[1])):
        label = n.split("__")[-1]
        if label in ("distance", "angle_from_net", "is_rebound", "is_rush_mp") \
           or abs(c) > 0.3:
            print(f"    {label:<26}{c:+.4f}")

    cal_obj = fitted[chosen] if chosen else fitted["platt"]
    CALIBRATOR_PATH.write_text(json.dumps(cal_obj.to_dict(), indent=2))
    print(f"\n  Saved {CALIBRATOR_PATH.relative_to(ROOT)} "
          f"(method={cal_obj.method}, adopted={bool(chosen)})")


if __name__ == "__main__":
    main()
