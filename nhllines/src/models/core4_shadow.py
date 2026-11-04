"""
core4: the 4-variable win model the Nov 2026 feature search picked
(feature_search/README.md). Run as a SHADOW for the 2026-27 season: main.py
logs its prediction for every game where both teams have played at least
`min_gp` games, to data/shadow_core4_log.jsonl, and never serves it.

    logit = intercept + a*elo_diff + b*xg_diff_rate_diff + c*home_b2b + d*away_b2b

Inputs come from the same live sources the served models use, so there is no
second feature pipeline to drift:
  elo_diff           elo_production.get_live_elo_ratings() (home - away)
  xg_diff_rate_diff  xg_production.compute_serving_features()
  home_b2b/away_b2b  the live rest-day feed, as 0.0/1.0

The coefficients are frozen (feature_search/fit_core4.py). The search computed
Elo from 2014-15 while serving computes it from 2022-23; by 2026-27 the two
correlate at 0.9999, so the difference is negligible.
"""

import json
import math
from pathlib import Path

COEFFICIENTS_PATH = Path(__file__).resolve().parents[2] / "ml_models" / "core4_coefficients.json"


def model_exists() -> bool:
    return COEFFICIENTS_PATH.exists()


def load_model() -> dict:
    """The persisted artifact: coefficients, feature list, min_gp, version."""
    return json.loads(COEFFICIENTS_PATH.read_text())


def predict(model: dict, elo_diff: float, xg_diff_rate_diff: float,
            home_b2b: bool, away_b2b: bool) -> float:
    """P(home win)."""
    c = model["coefficients"]
    x = {"elo_diff": float(elo_diff), "xg_diff_rate_diff": float(xg_diff_rate_diff),
         "home_b2b": 1.0 if home_b2b else 0.0, "away_b2b": 1.0 if away_b2b else 0.0}
    if set(x) != set(model["feature_columns"]):
        raise ValueError(f"core4 artifact expects {model['feature_columns']}, got {sorted(x)}")
    logit = c["intercept"] + sum(c[k] * v for k, v in x.items())
    return 1.0 / (1.0 + math.exp(-logit))
