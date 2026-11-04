"""Fit the 4-variable shadow model ("core4") and write
ml_models/core4_coefficients.json.

core4 is the feature search's winner (see README.md here): elo_diff,
xg_diff_rate_diff, home_b2b, away_b2b. L2 logistic, C=0.1, fit on every
2015-16..2025-26 game where both teams had played >= 5 games. No Platt step:
a 4-variable logistic on 15k games is already calibrated, and a calibrator
would need a held-out season we'd rather keep in training.

Frozen for the 2026-27 season on purpose: the shadow is a live test, and a
model refit mid-test isn't the model being tested. Coefficients are stored in
raw feature units, so serving computes the logit directly.

Usage, from nhllines/feature_search:  ../.venv/bin/python fit_core4.py
"""
import json
import os
from pathlib import Path

os.environ["NO_GOALIE"] = "1"
import numpy as np
import harness as H

FEATURES = ["elo_diff", "xg_diff_rate_diff", "home_b2b", "away_b2b"]
OUT = Path(__file__).resolve().parents[1] / "ml_models" / "core4_coefficients.json"

X, y, season = H.load()
seasons = H.CV_SEASONS + H.TEST_SEASONS
mask = np.isin(season, seasons)
j = [H.ALL.index(f) for f in FEATURES]
Xf = X[mask][:, j]
mu, sd = Xf.mean(0), Xf.std(0)
beta = H.fit((Xf - mu) / sd, y[mask])

coef = beta[1:] / sd
intercept = beta[0] - float(np.sum(beta[1:] * mu / sd))

# The raw coefficients must reproduce the standardised fit exactly.
p_std = H.predict(beta, (Xf - mu) / sd)
p_raw = 1 / (1 + np.exp(-(intercept + Xf @ coef)))
assert np.abs(p_std - p_raw).max() < 1e-9

OUT.write_text(json.dumps({
    "model_version": "core4-v1",
    "feature_columns": FEATURES,
    "coefficients": {**dict(zip(FEATURES, coef.tolist())), "intercept": float(intercept)},
    "trained_on_seasons": seasons,
    "min_gp": H.MIN_GP,
    "C": H.C,
    "n_games": int(mask.sum()),
    "note": "Shadow model (never served). Frozen for 2026-27; see feature_search/README.md.",
}, indent=2) + "\n")
print(f"wrote {OUT} from {mask.sum()} games")
for f, c, b in zip(FEATURES, coef, beta[1:]):
    print(f"  {f:<20} raw {c:+.5f}   per 1 SD {b:+.3f}")
print(f"  intercept {intercept:+.4f}")
