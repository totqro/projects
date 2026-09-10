#!/usr/bin/env python3
"""
The xG model: five features.

    python xg_model.py                          # train, evaluate, save
    python xg_model.py --model tree             # gradient boosting instead
    python xg_model.py --shot 12 15 WRIST 1 PP_5v4     # score one shot

Five features carry ~99% of what a linear model can extract from this data
(see ablate_features.py): the remaining 35 columns in the schema add +0.0004
AUC and make per-situation calibration measurably worse. Fewer features also
means the model is explainable to someone who is not going to read the code,
which for this project matters as much as the last decimal of AUC.

    distance         feet from the net
    angle_from_net   0 = straight on, 90 = on the goal line, >90 = behind it
    shot_type        WRIST / SNAP / SLAP / TIP / BACK / DEFL / WRAP / UNKNOWN
    is_rebound       shot within 3s of a prior shot, close to it
    situation        strength state, with 6v5 split by cause

Default is logistic regression, not the tree: it is better calibrated per
situation (0.1256 vs 0.1543), it gives a readable coefficient per shot type
and situation, and it gives up only 0.008 AUC. Calibration is what an xG
model is for -- the totals have to be right.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.data.schema import assert_no_holdout_leak

FEATURES = ["distance", "angle_from_net", "shot_type", "is_rebound", "situation"]
NUMERIC = ["distance", "angle_from_net", "is_rebound"]
CATEGORICAL = ["shot_type", "situation"]

VALID_SEASON, TEST_SEASON = 2024, 2025
MODEL_PATH = ROOT / "data" / "xg_model.joblib"


def build(kind: str) -> Pipeline:
    if kind == "logistic":
        return Pipeline([
            ("prep", ColumnTransformer([
                ("num", StandardScaler(), NUMERIC),
                ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=30),
                 CATEGORICAL),
            ])),
            ("clf", LogisticRegression(max_iter=2000)),
        ])
    return Pipeline([
        ("prep", ColumnTransformer([
            ("num", "passthrough", NUMERIC),
            ("cat", OrdinalEncoder(handle_unknown="use_encoded_value",
                                   unknown_value=-1), CATEGORICAL),
        ])),
        ("clf", HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.1, early_stopping=True,
            categorical_features=[len(NUMERIC), len(NUMERIC) + 1],
            random_state=0)),
    ])


def predict_xg(model, shots: pd.DataFrame) -> np.ndarray:
    """xG for each row of `shots`. Needs the five FEATURES columns."""
    missing = [c for c in FEATURES if c not in shots.columns]
    if missing:
        raise ValueError(f"missing required feature column(s): {missing}")
    return model.predict_proba(shots[FEATURES])[:, 1]


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------
def report_headline(name, y, p):
    print(f"  {name:<24} AUC {roc_auc_score(y, p):.4f}   "
          f"log loss {log_loss(y, p, labels=[0,1]):.5f}   "
          f"sum(xG)/goals {p.sum()/y.sum():.4f}")


def report_calibration_curve(y, p, bins=10):
    """Are shots we call 10% actually 10%? The core question for an xG model."""
    print("\n  Calibration by predicted-probability decile")
    print(f"    {'bucket':<16}{'n':>8}{'mean xG':>10}{'actual':>10}{'ratio':>8}")
    q = pd.qcut(p, bins, duplicates="drop")
    t = pd.DataFrame({"y": y.to_numpy(), "p": p, "q": q})
    for interval, g in t.groupby("q", observed=True):
        act = g.y.mean()
        ratio = g.p.mean() / act if act > 0 else float("nan")
        print(f"    {f'{interval.left:.3f}-{interval.right:.3f}':<16}"
              f"{len(g):>8,}{g.p.mean():>10.4f}{act:>10.4f}{ratio:>8.3f}")


def report_by_situation(df, p):
    print("\n  Calibration by situation")
    t = df.assign(_p=p)
    print(f"    {'situation':<22}{'n':>8}{'goals':>8}{'xG':>10}{'ratio':>8}")
    errs = []
    for sit, g in t.groupby("situation"):
        if len(g) < 300 or g.goal.sum() == 0:
            continue
        ratio = g._p.sum() / g.goal.sum()
        errs.append(abs(ratio - 1))
        print(f"    {sit:<22}{len(g):>8,}{int(g.goal.sum()):>8,}"
              f"{g._p.sum():>10.1f}{ratio:>8.3f}")
    print(f"    {'mean abs error':<22}{'':>26}{np.mean(errs):>8.4f}")


def report_coefficients(model):
    clf = model.named_steps["clf"]
    if not hasattr(clf, "coef_"):
        return
    names = model.named_steps["prep"].get_feature_names_out()
    coefs = clf.coef_[0]
    print("\n  What the model learned (log-odds; + means more likely to score)")
    for n, c in sorted(zip(names, coefs), key=lambda r: -r[1]):
        label = n.split("__")[-1]
        bar = ("+" if c > 0 else "-") * min(int(abs(c) * 10), 30)
        print(f"    {label:<28}{c:+.3f}  {bar}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", choices=["logistic", "tree"], default="logistic")
    ap.add_argument("--shot", nargs=5,
                    metavar=("DIST", "ANGLE", "TYPE", "REBOUND", "SITUATION"),
                    help="score a single shot with the saved model")
    args = ap.parse_args()

    if args.shot:
        import joblib
        if not MODEL_PATH.exists():
            sys.exit("No saved model. Run `python xg_model.py` first.")
        model = joblib.load(MODEL_PATH)
        d, a, t, r, s = args.shot
        shot = pd.DataFrame([{"distance": float(d), "angle_from_net": float(a),
                              "shot_type": t, "is_rebound": int(r), "situation": s}])
        print(f"xG = {predict_xg(model, shot)[0]:.4f}")
        return

    df = pd.read_parquet(ROOT / "data" / "shots.parquet")
    train = df[df.season < VALID_SEASON]
    valid = df[df.season == VALID_SEASON]
    test = df[df.season == TEST_SEASON]
    print(f"Five-feature xG model ({args.model})")
    print(f"train {len(train):,} (<{VALID_SEASON})  valid {len(valid):,}  "
          f"test {len(test):,} ({TEST_SEASON})\n")
    print("Features: " + ", ".join(FEATURES))

    assert_no_holdout_leak(train)
    model = build(args.model)
    model.fit(train[FEATURES], train.goal)

    print("\nHeadline")
    for name, part in [("valid " + str(VALID_SEASON), valid),
                       ("test " + str(TEST_SEASON), test)]:
        report_headline(f"ours {name}", part.goal, predict_xg(model, part))
    for name, part in [("valid " + str(VALID_SEASON), valid),
                       ("test " + str(TEST_SEASON), test)]:
        report_headline(f"moneypuck {name}", part.goal,
                        part.mp_xg.clip(1e-6, 1 - 1e-6).to_numpy())

    p_test = predict_xg(model, test)
    print(f"\nHeld-out {TEST_SEASON}")
    report_calibration_curve(test.goal, p_test)
    report_by_situation(test, p_test)
    report_coefficients(model)

    import joblib
    joblib.dump(model, MODEL_PATH)
    print(f"\nSaved {MODEL_PATH.relative_to(ROOT)} "
          f"({MODEL_PATH.stat().st_size/1000:.0f} KB)")


if __name__ == "__main__":
    main()
