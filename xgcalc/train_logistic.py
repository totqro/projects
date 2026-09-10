#!/usr/bin/env python3
"""
Logistic-regression xG baseline.

    python train_logistic.py                      # default: --strength situation
    python train_logistic.py --strength bucket    # coarse EV/PP/SH instead
    python train_logistic.py --compare            # run every strength option

The strength state enters the model as ONE selectable categorical, so the
encodings can be compared like for like:

  situation  15 levels — 5v5, PP 5v4/5v3/4v3, 3v3, 4v4, SH, and 6v5 split by
             cause (delayed penalty vs pulled goalie), plus shooting at an
             empty net. This is the default.
  state      raw skater counts ("5v5", "6v5", ...), blind to WHY the net is
             empty and to pulled goalies inflating the count.
  bucket     coarse EV / PP / SH.
  none       no strength term at all — the floor to beat.

Deliberately a baseline: linear in the features, so it will lose to a boosted
model on the sharp distance/angle interactions. Its job is calibration and a
readable coefficient per situation.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))
from src.data.schema import (assert_no_holdout_leak, BINARY_FEATURES, CATEGORICAL_FEATURES,
                             LABEL_COLUMN, NUMERIC_FEATURES)

DATA_DIR = Path(__file__).resolve().parent / "data"

# The strength term is swappable; every other categorical is always included.
STRENGTH_OPTIONS = {
    "situation": "situation",
    "state": "strength_state",
    "bucket": "strength_bucket",
    "none": None,
}
# All the strength-ish columns, removed wholesale before the chosen one is
# added back — otherwise `--strength bucket` would still leak the fine-grained
# situation in through another column and the comparison would be meaningless.
STRENGTH_COLUMNS = {"situation", "strength_state", "strength_bucket"}
STRENGTH_NUMERICS = {"shooting_skaters", "defending_skaters", "skater_differential"}

# Hold out the most recent season entirely; the one before it tunes nothing
# here but is reported so the gap between them is visible.
TEST_SEASON = 2025
VALID_SEASON = 2024


def build_features(strength: str):
    cats = [c for c in CATEGORICAL_FEATURES if c not in STRENGTH_COLUMNS]
    col = STRENGTH_OPTIONS[strength]
    if col:
        cats.append(col)
    # Skater counts are themselves a strength encoding — drop them unless the
    # model is meant to see raw counts, so each option is tested honestly.
    nums = [c for c in NUMERIC_FEATURES
            if c not in STRENGTH_NUMERICS or strength == "state"]
    return nums, BINARY_FEATURES, cats


def evaluate(name, y, p, base_rate):
    ll = log_loss(y, p, labels=[0, 1])
    auc = roc_auc_score(y, p)
    # Calibration: predicted goals vs actual. A good xG model must total
    # correctly, not just rank well.
    ratio = p.sum() / y.sum()
    print(f"  {name:<22} log_loss {ll:.5f}   AUC {auc:.4f}   "
          f"sum(xG)/goals {ratio:.4f}")
    return {"model": name, "log_loss": ll, "auc": auc, "calibration": ratio}


def run(df, strength, verbose=True):
    nums, bins, cats = build_features(strength)
    feats = nums + bins + cats

    train = df[df.season < VALID_SEASON]
    assert_no_holdout_leak(train)
    valid = df[df.season == VALID_SEASON]
    test = df[df.season == TEST_SEASON]

    pipe = Pipeline([
        ("prep", ColumnTransformer([
            ("num", StandardScaler(), nums + bins),
            ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=30), cats),
        ])),
        ("clf", LogisticRegression(max_iter=2000, C=1.0)),
    ])
    pipe.fit(train[feats], train[LABEL_COLUMN])

    results = []
    for label, part in [("valid " + str(VALID_SEASON), valid),
                        ("test " + str(TEST_SEASON), test)]:
        p = pipe.predict_proba(part[feats])[:, 1]
        if verbose:
            r = evaluate(f"ours ({strength}) {label}", part[LABEL_COLUMN], p,
                         part[LABEL_COLUMN].mean())
            r["split"] = label
            results.append(r)
    return pipe, feats, results


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--strength", choices=list(STRENGTH_OPTIONS), default="situation")
    ap.add_argument("--compare", action="store_true",
                    help="train once per strength option and compare")
    args = ap.parse_args()

    path = DATA_DIR / "shots.parquet"
    if not path.exists():
        sys.exit(f"No dataset at {path}. Run build_dataset.py first.")
    df = pd.read_parquet(path)
    print(f"Loaded {len(df):,} shots  |  train <{VALID_SEASON}, "
          f"valid {VALID_SEASON}, test {TEST_SEASON}\n")

    # MoneyPuck's own model on the same held-out rows — the number to beat.
    print("Benchmark (MoneyPuck xG, same rows)")
    for label, part in [(f"valid {VALID_SEASON}", df[df.season == VALID_SEASON]),
                        (f"test {TEST_SEASON}", df[df.season == TEST_SEASON])]:
        evaluate(f"moneypuck {label}", part[LABEL_COLUMN],
                 part.mp_xg.clip(1e-6, 1 - 1e-6).to_numpy(), part[LABEL_COLUMN].mean())

    options = list(STRENGTH_OPTIONS) if args.compare else [args.strength]
    print("\nOurs")
    for opt in options:
        run(df, opt)

    if not args.compare:
        pipe, feats, _ = run(df, args.strength, verbose=False)
        show_situation_coefficients(pipe, args.strength)


def show_situation_coefficients(pipe, strength):
    """Print the learned coefficient per strength level — the readable payoff
    of a linear baseline."""
    col = STRENGTH_OPTIONS[strength]
    if not col:
        return
    prep = pipe.named_steps["prep"]
    names = prep.get_feature_names_out()
    coefs = pipe.named_steps["clf"].coef_[0]
    rows = [(n.split("__")[-1], c) for n, c in zip(names, coefs) if f"{col}_" in n]
    if not rows:
        return
    print(f"\nLearned effect per '{col}' level (log-odds vs the average shot):")
    for name, c in sorted(rows, key=lambda r: -r[1]):
        bar = "#" * min(int(abs(c) * 12), 40)
        print(f"  {name.replace(col + '_', ''):<24} {c:+.3f}  {bar}")


if __name__ == "__main__":
    main()
