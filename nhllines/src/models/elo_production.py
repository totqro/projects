"""
Production wiring for the model-gate winner: Elo + home-ice logistic,
Platt-calibrated (roadmap step: "wire the gate winner into main.py").

Two artifacts are persisted to `ml_models/` at retrain time (called from
`build_training_set.py`, i.e. weekly alongside the dataset refresh):

  calibrator.json       — calibrator.to_dict(), reloaded with
                           src.models.calibration.load_calibrator(). This is
                           the ONLY thing that function knows how to read, so
                           it stays a flat calibrator dict, not a bundle.
  elo_coefficients.json — the underlying Elo + home-ice logistic regression
                           coefficients (intercept, elo_diff, rest_diff,
                           home_b2b, away_b2b), unscaled so the logit can be
                           computed directly from raw feature values. This is
                           the base model the calibrator was fit on top of —
                           without it there is nothing to calibrate.

Both are fit on the identical train/calibration split used by
`calibration.fit_production_calibrator`: the Elo logistic trains on every
season but the most recent, and the calibrator is fit on that held-out most
recent season. Reusing `elo_baseline.evaluate()` for the coefficients keeps
that split defined in exactly one place.
"""

import json
import math
from pathlib import Path

from .calibration import DEFAULT_SEASONS, fit_production_calibrator, load_calibrator
from .elo_baseline import ELO_FEATURE_COLUMNS, compute_live_ratings, evaluate as evaluate_elo

ML_MODELS_DIR = Path(__file__).resolve().parents[2] / "ml_models"
CALIBRATOR_PATH = ML_MODELS_DIR / "calibrator.json"
COEFFICIENTS_PATH = ML_MODELS_DIR / "elo_coefficients.json"


def fit_and_persist(seasons: list = None, csv_path: str = "data/training_set.csv") -> dict:
    """
    Fit the production Elo model + Platt calibrator and write both artifacts
    to ml_models/. Returns a summary dict for logging/reporting.
    """
    seasons = seasons or DEFAULT_SEASONS
    elo_eval = evaluate_elo(seasons, csv_path)
    calibrator = fit_production_calibrator("elo", "platt", seasons, csv_path)

    ML_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    CALIBRATOR_PATH.write_text(json.dumps(calibrator.to_dict(), indent=2))
    COEFFICIENTS_PATH.write_text(json.dumps({
        "feature_columns": ELO_FEATURE_COLUMNS,
        "coefficients": elo_eval["coefficients"],
        "trained_on_seasons": [s for s in seasons if s != elo_eval["test_season"]],
        "held_out_calibration_season": elo_eval["test_season"],
    }, indent=2))

    return {
        "seasons": seasons,
        "held_out_calibration_season": elo_eval["test_season"],
        "calibrator_method": calibrator.method,
        "coefficients": elo_eval["coefficients"],
    }


def load_production_model() -> tuple:
    """Load (coefficients dict, calibrator) persisted by fit_and_persist()."""
    coefs = json.loads(COEFFICIENTS_PATH.read_text())["coefficients"]
    calibrator = load_calibrator(json.loads(CALIBRATOR_PATH.read_text()))
    return coefs, calibrator


def production_model_exists() -> bool:
    return CALIBRATOR_PATH.exists() and COEFFICIENTS_PATH.exists()


def get_live_elo_ratings(seasons: list = None) -> dict:
    """
    Current Elo rating per team, computed from every completed game across
    `seasons` — the pregame rating each team carries into its NEXT game.
    """
    from src.data.historical_dataset import fetch_season_games_full

    seasons = seasons or DEFAULT_SEASONS
    all_games = []
    for season in seasons:
        all_games.extend(fetch_season_games_full(season, verbose=False))
    return compute_live_ratings(all_games, current_season=seasons[-1])


def predict_calibrated(coefs: dict, calibrator, elo_diff: float, rest_diff: float,
                       home_b2b: float, away_b2b: float) -> tuple:
    """
    Apply the Elo + home-ice logistic coefficients to raw feature values, then
    the Platt calibrator, to get P(home win). Returns (p_calibrated, p_raw).
    """
    logit = (coefs["intercept"]
             + coefs["elo_diff"] * elo_diff
             + coefs["rest_diff"] * rest_diff
             + coefs["home_b2b"] * home_b2b
             + coefs["away_b2b"] * away_b2b)
    p_raw = 1.0 / (1.0 + math.exp(-logit))
    p_cal = float(calibrator.predict([p_raw])[0])
    return p_cal, p_raw
