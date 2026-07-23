"""
Production wiring for the model-gate ablation winner: the 44-feature
point-in-time logistic regression with the goalie block dropped (xG in,
goalie out), Platt-calibrated. This replaces the Elo-only win probability in
main.py — see model_gate.py --ablation, which showed it's the only variant
to beat the Elo + home-ice baseline on BOTH held-out log loss and Brier
(0.6881 / 0.2473 vs Elo's 0.6929 / 0.2496).

Two artifacts are persisted to `ml_models/` at retrain time (called from
`build_training_set.py`, i.e. weekly alongside the dataset refresh):

  xg_calibrator.json    — calibrator.to_dict(), reloaded with
                           src.models.calibration.load_calibrator().
  xg_coefficients.json  — the underlying drop-goalie logistic regression
                           coefficients (intercept + one weight per
                           XG_FEATURE_COLUMNS entry), unscaled so the logit
                           can be computed directly from raw feature values.

Both are fit on the identical train/calibration split used by
`calibration.fit_production_calibrator`: the logistic trains on every season
but the most recent, and the calibrator is fit on that held-out most recent
season — same split calibration.py's "xg" model branch uses, so the raw
probabilities the calibrator is fit on are the exact ones the persisted
coefficients reproduce (same rows, same columns, same C, same solver).

Live serving needs the same point-in-time features the training set uses,
computed as of "right now" instead of as of a past game's date. That replay
is done by src.data.historical_dataset.build_live_state(), which is
deliberately lag-tolerant for MoneyPuck xG (unlike the training-set builder,
which hard-fails on a missing xG join for a covered season): MoneyPuck
publishes with a delay, so a team's xG state simply carries forward from its
last covered game rather than resetting to the neutral default mid-season.
Rest days / back-to-back are NOT re-derived from the state replay — like
elo_production.py's predict_calibrated(), this module takes them as
already-converted inputs, and main.py's _xg_win_prob() applies the same
"+1, capped at 7" conversion _elo_win_prob() does, so both shipped models
read the live rest-day feed identically.
"""

import csv
import json
import math
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from src.data.historical_dataset import (
    MONEYPUCK_SEASONS,
    XG_FEATURE_COLUMNS,
    build_live_state,
    fetch_season_games_full,
    snapshot_team_state,
)
from src.data.moneypuck_data import load_moneypuck_xg
from src.models.calibration import DEFAULT_SEASONS, fit_production_calibrator, load_calibrator

ML_MODELS_DIR = Path(__file__).resolve().parents[2] / "ml_models"
CALIBRATOR_PATH = ML_MODELS_DIR / "xg_calibrator.json"
COEFFICIENTS_PATH = ML_MODELS_DIR / "xg_coefficients.json"


def _load_rows(csv_path: str) -> list:
    with open(csv_path) as f:
        return list(csv.DictReader(f))


def _fit_logistic_coefficients(rows: list, test_season: str) -> dict:
    """Fit the drop-goalie logistic on every season but `test_season`
    (matching fit_production_calibrator's train split), and return unscaled
    coefficients (raw feature units) so serving can compute the logit
    directly without carrying a fitted StandardScaler around. Mirrors
    elo_baseline.evaluate()'s unscaling."""
    train = [r for r in rows if r["season"] != test_season]
    X = np.array([[float(r[c]) for c in XG_FEATURE_COLUMNS] for r in train])
    y = np.array([int(r["home_win"]) for r in train])

    scaler = StandardScaler().fit(X)
    # liblinear: matches calibration.py's _fit_predict_logistic exactly (same
    # data, columns, C, solver) so the two fits are numerically identical and
    # the persisted coefficients reproduce the probabilities the calibrator
    # was actually fit on.
    model = LogisticRegression(max_iter=2000, C=0.1, solver="liblinear")
    model.fit(scaler.transform(X), y)

    raw_coef = model.coef_[0] / scaler.scale_
    raw_intercept = model.intercept_[0] - np.sum(model.coef_[0] * scaler.mean_ / scaler.scale_)
    coefs = dict(zip(XG_FEATURE_COLUMNS, raw_coef.tolist()))
    coefs["intercept"] = float(raw_intercept)
    return coefs


def fit_and_persist(seasons: list = None, csv_path: str = "data/training_set.csv") -> dict:
    """
    Fit the production drop-goalie logistic + Platt calibrator and write both
    artifacts to ml_models/. Returns a summary dict for logging/reporting.
    """
    seasons = seasons or DEFAULT_SEASONS
    rows = _load_rows(csv_path)
    present = sorted(set(r["season"] for r in rows))
    if len(present) < 2:
        raise ValueError("Need >= 2 seasons in the training set to fit the production xG model")
    test_season = present[-1]

    coefs = _fit_logistic_coefficients(rows, test_season)
    calibrator = fit_production_calibrator("xg", "platt", seasons, csv_path)

    ML_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    CALIBRATOR_PATH.write_text(json.dumps(calibrator.to_dict(), indent=2))
    COEFFICIENTS_PATH.write_text(json.dumps({
        "feature_columns": XG_FEATURE_COLUMNS,
        "coefficients": coefs,
        "trained_on_seasons": [s for s in present if s != test_season],
        "held_out_calibration_season": test_season,
    }, indent=2))

    return {
        "seasons": seasons,
        "held_out_calibration_season": test_season,
        "calibrator_method": calibrator.method,
        "coefficients": coefs,
    }


def load_production_model() -> tuple:
    """Load (coefficients dict, calibrator) persisted by fit_and_persist()."""
    coefs = json.loads(COEFFICIENTS_PATH.read_text())["coefficients"]
    calibrator = load_calibrator(json.loads(CALIBRATOR_PATH.read_text()))
    return coefs, calibrator


def production_model_exists() -> bool:
    return CALIBRATOR_PATH.exists() and COEFFICIENTS_PATH.exists()


def predict_calibrated(coefs: dict, calibrator, features: dict) -> tuple:
    """
    Apply the drop-goalie logistic coefficients to raw point-in-time feature
    values, then the Platt calibrator, to get P(home win). `features` must
    carry every key in XG_FEATURE_COLUMNS, already in training convention
    (rest_days capped at 7, b2b as 0.0/1.0 — see main.py's _xg_win_prob).
    Returns (p_calibrated, p_raw).
    """
    logit = coefs["intercept"] + sum(
        coefs[c] * float(features[c]) for c in XG_FEATURE_COLUMNS)
    p_raw = 1.0 / (1.0 + math.exp(-logit))
    p_cal = float(calibrator.predict([p_raw])[0])
    return p_cal, p_raw


def get_live_feature_state(seasons: list = None) -> dict:
    """
    Point-in-time state for every team, built by replaying every completed
    game across `seasons` in chronological order (build_live_state()) —
    the serving-time counterpart to the point-in-time rows the training set
    is built from. Compute this ONCE per run and reuse it for every game via
    compute_serving_features(), rather than re-fetching/re-replaying per game.
    """
    seasons = seasons or DEFAULT_SEASONS
    all_games = []
    for season in seasons:
        all_games.extend(fetch_season_games_full(season, verbose=False))

    xg_seasons = sorted(set(seasons) & MONEYPUCK_SEASONS)
    xg_data = load_moneypuck_xg(xg_seasons) if xg_seasons else {}

    team_states, h2h_results = build_live_state(all_games, xg_data=xg_data)
    return {
        "team_states": team_states,
        "h2h_results": h2h_results,
        "current_season": seasons[-1],
        "as_of_date": max((g["date"] for g in all_games), default=""),
    }


def compute_serving_features(state: dict, home: str, away: str,
                             home_rest_days: float, away_rest_days: float,
                             home_b2b: bool, away_b2b: bool) -> dict:
    """
    Build the XG_FEATURE_COLUMNS feature dict for an upcoming (home, away)
    game from the shared live state produced by get_live_feature_state().

    `home_rest_days` / `away_rest_days` / `home_b2b` / `away_b2b` are taken
    as-is, already in training convention — the caller (main.py's
    _xg_win_prob) is responsible for the same "+1, capped at 7" conversion
    _elo_win_prob() applies, so both shipped models read the live rest-day
    feed identically.
    """
    season = state["current_season"]
    team_states = state["team_states"]
    h2h_results = state["h2h_results"]
    as_of_date = state["as_of_date"]

    h = snapshot_team_state(team_states, season, home, as_of_date)
    a = snapshot_team_state(team_states, season, away, as_of_date)

    # Already converted by the caller (see docstring) — used as-is.
    home_rest = home_rest_days
    away_rest = away_rest_days
    home_b2b_val = 1.0 if home_b2b else 0.0
    away_b2b_val = 1.0 if away_b2b else 0.0

    pair = frozenset((home, away))
    prior = h2h_results.get(pair, [])[-10:]
    h2h_rate = (sum(1 for _, w in prior if w == home) / len(prior)) if prior else 0.5

    features = {
        "home_gp": h["gp"], "home_win_pct": h["win_pct"], "home_points_pct": h["points_pct"],
        "home_gf_pg": h["gf_pg"], "home_ga_pg": h["ga_pg"],
        "home_home_win_pct": h["home_win_pct"],
        "home_form_win_pct": h["form_win_pct"], "home_form_gf": h["form_gf"], "home_form_ga": h["form_ga"],
        "home_rest_days": home_rest, "home_b2b": home_b2b_val,
        "home_streak": h["streak"], "home_trend": h["trend"],

        "away_gp": a["gp"], "away_win_pct": a["win_pct"], "away_points_pct": a["points_pct"],
        "away_gf_pg": a["gf_pg"], "away_ga_pg": a["ga_pg"],
        "away_road_win_pct": a["road_win_pct"],
        "away_form_win_pct": a["form_win_pct"], "away_form_gf": a["form_gf"], "away_form_ga": a["form_ga"],
        "away_rest_days": away_rest, "away_b2b": away_b2b_val,
        "away_streak": a["streak"], "away_trend": a["trend"],

        "home_xgf_per60": h["xgf_per60"], "home_xga_per60": h["xga_per60"],
        "home_high_danger_xg_share": h["high_danger_xg_share"],
        "home_xg_luck_for": h["xg_luck_for"], "home_xg_luck_against": h["xg_luck_against"],
        "away_xgf_per60": a["xgf_per60"], "away_xga_per60": a["xga_per60"],
        "away_high_danger_xg_share": a["high_danger_xg_share"],
        "away_xg_luck_for": a["xg_luck_for"], "away_xg_luck_against": a["xg_luck_against"],

        "win_pct_diff": h["win_pct"] - a["win_pct"],
        "points_pct_diff": h["points_pct"] - a["points_pct"],
        "form_diff": h["form_win_pct"] - a["form_win_pct"],
        "goal_diff_rate_diff": (h["gf_pg"] - h["ga_pg"]) - (a["gf_pg"] - a["ga_pg"]),
        "xg_diff_rate_diff": ((h["xgf_per60"] - h["xga_per60"])
                              - (a["xgf_per60"] - a["xga_per60"])),
        "rest_diff": home_rest - away_rest,
        "h2h_home_win_rate": h2h_rate,
        "h2h_meetings": len(prior),
    }

    missing = set(XG_FEATURE_COLUMNS) - set(features)
    extra = set(features) - set(XG_FEATURE_COLUMNS)
    if missing or extra:
        raise ValueError(
            f"compute_serving_features() drifted from XG_FEATURE_COLUMNS: "
            f"missing={sorted(missing)} extra={sorted(extra)}")

    return features
