"""
MLB win probability: gated, calibrated, pre-game only.
======================================================
Two models, one rule.

  * Baseline: Elo + home field. A logistic on `elo_diff` alone; its intercept
    is home-field advantage. Two parameters.
  * Candidate: the same logistic plus the probable starters, bullpens and
    shrunk run differential (historical_dataset.WIN_FEATURE_COLUMNS).

The candidate ships only if it beats the baseline on BOTH log loss and Brier
on a held-out season. Accuracy is reported but never decides anything: it is
noisy, and it rewards overconfident models.

Calibration follows the same rule. Platt scaling is fit on one held-out season
and scored on a later one it never saw. It is adopted only if it beats the raw
probabilities on both metrics there. Otherwise the raw logistic ships.

Everything a run needs is persisted to one JSON file (ml_models/win_model.json):
the chosen model, unscaled coefficients, the calibrator, the seasons used, and
the gate numbers that justified the choice.
"""

import json
import math
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss
from sklearn.preprocessing import StandardScaler

from src.data.historical_dataset import ELO_FEATURE_COLUMNS, WIN_FEATURE_COLUMNS

ML_MODELS_DIR = Path(__file__).resolve().parents[2] / "ml_models"
WIN_MODEL_PATH = ML_MODELS_DIR / "win_model.json"

MODELS = {
    "elo": {"columns": ELO_FEATURE_COLUMNS, "C": 1.0,
            "label": "Elo + home field (baseline, 2 params)"},
    "pitcher": {"columns": WIN_FEATURE_COLUMNS, "C": 1.0,
                "label": f"Elo + starters + bullpen + run diff ({len(WIN_FEATURE_COLUMNS) + 1} params)"},
}
MODEL_VERSIONS = {"elo": "mlb-elo-v1", "pitcher": "mlb-pitcher-logit-v1"}

# A season needs at least this many games to serve as a calibration or test
# season. A partial current season below it is used for training only.
MIN_SEASON_GAMES = 1000

_EPS = 1e-6


# --------------------------------------------------------------------------- #
# Fitting                                                                      #
# --------------------------------------------------------------------------- #
def fit_logistic(rows: list, columns: list, C: float = 1.0) -> dict:
    """Scaled logistic regression, returned as UNSCALED coefficients so
    serving needs no scaler: logit = intercept + sum(coef * raw feature)."""
    X = np.array([[float(r[c]) for c in columns] for r in rows])
    y = np.array([int(r["home_win"]) for r in rows])
    scaler = StandardScaler().fit(X)
    model = LogisticRegression(C=C, max_iter=2000, solver="liblinear")
    model.fit(scaler.transform(X), y)
    raw = model.coef_[0] / scaler.scale_
    intercept = model.intercept_[0] - float(np.sum(model.coef_[0] * scaler.mean_ / scaler.scale_))
    coefs = dict(zip(columns, (float(v) for v in raw)))
    coefs["intercept"] = float(intercept)
    return coefs


def raw_prob(coefs: dict, features: dict, columns: list) -> float:
    z = coefs["intercept"] + sum(coefs[c] * float(features[c]) for c in columns)
    return 1.0 / (1.0 + math.exp(-z))


def raw_probs(coefs: dict, rows: list, columns: list) -> np.ndarray:
    return np.array([raw_prob(coefs, r, columns) for r in rows])


class Calibrator:
    """Identity (a=1, b=0) or Platt: sigmoid(a * logit(p) + b)."""

    def __init__(self, method: str = "identity", a: float = 1.0, b: float = 0.0):
        self.method, self.a, self.b = method, a, b

    @classmethod
    def fit_platt(cls, p, y):
        z = _logit(p).reshape(-1, 1)
        lr = LogisticRegression(solver="liblinear", C=1e6)
        lr.fit(z, np.asarray(y, dtype=int))
        return cls("platt", float(lr.coef_[0, 0]), float(lr.intercept_[0]))

    def __call__(self, p):
        if self.method == "identity":
            return _clip(p)
        return _clip(1.0 / (1.0 + np.exp(-(self.a * _logit(p) + self.b))))

    def to_dict(self):
        return {"method": self.method, "a": self.a, "b": self.b}

    @classmethod
    def from_dict(cls, d):
        return cls(d["method"], float(d.get("a", 1.0)), float(d.get("b", 0.0)))


def _clip(p):
    return np.clip(np.asarray(p, dtype=float), _EPS, 1 - _EPS)


def _logit(p):
    p = _clip(p)
    return np.log(p / (1 - p))


# --------------------------------------------------------------------------- #
# Metrics                                                                      #
# --------------------------------------------------------------------------- #
def expected_calibration_error(p, y, n_bins: int = 10) -> float:
    p, y = _clip(p), np.asarray(y, dtype=int)
    idx = np.clip((p * n_bins).astype(int), 0, n_bins - 1)
    ece = 0.0
    for b in range(n_bins):
        m = idx == b
        if m.any():
            ece += m.mean() * abs(p[m].mean() - y[m].mean())
    return float(ece)


def win_metrics(p, y) -> dict:
    p, y = _clip(p), np.asarray(y, dtype=int)
    if len(y) == 0:
        return {"n": 0}
    return {
        "n": int(len(y)),
        "accuracy": float(accuracy_score(y, p > 0.5)),
        "log_loss": float(log_loss(y, p, labels=[0, 1])),
        "brier": float(brier_score_loss(y, p)),
        "ece": expected_calibration_error(p, y),
    }


def reliability_table(p, y, n_bins: int = 10) -> list:
    p, y = _clip(p), np.asarray(y, dtype=int)
    idx = np.clip((p * n_bins).astype(int), 0, n_bins - 1)
    out = []
    for b in range(n_bins):
        m = idx == b
        if m.any():
            out.append({"lo": b / n_bins, "hi": (b + 1) / n_bins, "count": int(m.sum()),
                        "mean_pred": float(p[m].mean()), "frac_home_win": float(y[m].mean())})
    return out


# --------------------------------------------------------------------------- #
# Season splits                                                                #
# --------------------------------------------------------------------------- #
def full_seasons(rows: list) -> list:
    counts = {}
    for r in rows:
        counts[r["season"]] = counts.get(r["season"], 0) + 1
    return sorted(s for s, n in counts.items() if n >= MIN_SEASON_GAMES)


def by_seasons(rows: list, seasons) -> list:
    seasons = set(seasons)
    return [r for r in rows if r["season"] in seasons]


def always_home_probs(train_rows: list, n: int) -> np.ndarray:
    rate = float(np.mean([r["home_win"] for r in train_rows]))
    return np.full(n, rate)


# --------------------------------------------------------------------------- #
# Gate                                                                         #
# --------------------------------------------------------------------------- #
def evaluate_split(rows: list, test_season: int, train_seasons=None) -> dict:
    """Fit every model on `train_seasons` (default: every other season) and
    score the raw probabilities on `test_season`."""
    if train_seasons is None:
        train_seasons = [s for s in sorted({r["season"] for r in rows}) if s != test_season]
    train = by_seasons(rows, train_seasons)
    test = by_seasons(rows, [test_season])
    y = [r["home_win"] for r in test]

    out = {"test_season": test_season, "train_seasons": list(train_seasons),
           "n_train": len(train), "n_test": len(test),
           "always_home": win_metrics(always_home_probs(train, len(test)), y)}
    for name, spec in MODELS.items():
        coefs = fit_logistic(train, spec["columns"], spec["C"])
        out[name] = win_metrics(raw_probs(coefs, test, spec["columns"]), y)
    out["pitcher_beats_elo"] = (out["pitcher"]["log_loss"] < out["elo"]["log_loss"]
                                and out["pitcher"]["brier"] < out["elo"]["brier"])
    return out


def run_gate(rows: list) -> dict:
    """Primary gate: train on every full season before the last full season,
    test on the last full season. Plus leave-one-season-out over every full
    season, reported so a one-season fluke can't hide."""
    seasons = full_seasons(rows)
    if len(seasons) < 3:
        raise ValueError(f"Need >= 3 full seasons to gate; have {seasons}")
    test = seasons[-1]
    primary = evaluate_split(rows, test, [s for s in seasons if s < test])
    loso = [evaluate_split(rows, s, [x for x in seasons if x != s]) for s in seasons]
    return {
        "primary": primary,
        "loso": loso,
        "loso_pitcher_wins": sum(1 for r in loso if r["pitcher_beats_elo"]),
        "passed": primary["pitcher_beats_elo"],
        "winner": "pitcher" if primary["pitcher_beats_elo"] else "elo",
    }


def run_calibration_check(rows: list, model: str) -> dict:
    """Train on seasons before the last two full seasons, fit Platt on the
    second-to-last, score on the last. Adopt Platt only if it beats raw
    probabilities on both log loss and Brier."""
    seasons = full_seasons(rows)
    if len(seasons) < 3:
        return {"adopted": False, "reason": "fewer than 3 full seasons"}
    test_s, calib_s = seasons[-1], seasons[-2]
    spec = MODELS[model]
    train = by_seasons(rows, [s for s in seasons if s < calib_s])
    calib = by_seasons(rows, [calib_s])
    test = by_seasons(rows, [test_s])
    coefs = fit_logistic(train, spec["columns"], spec["C"])
    platt = Calibrator.fit_platt(raw_probs(coefs, calib, spec["columns"]),
                                 [r["home_win"] for r in calib])
    p_test = raw_probs(coefs, test, spec["columns"])
    y_test = [r["home_win"] for r in test]
    raw_m = win_metrics(p_test, y_test)
    platt_m = win_metrics(platt(p_test), y_test)
    return {
        "calibration_season": calib_s, "test_season": test_s,
        "raw": raw_m, "platt": platt_m, "platt_params": platt.to_dict(),
        "adopted": platt_m["log_loss"] < raw_m["log_loss"] and platt_m["brier"] < raw_m["brier"],
    }


# --------------------------------------------------------------------------- #
# Production fit                                                               #
# --------------------------------------------------------------------------- #
def fit_production(rows: list, model: str, use_platt: bool, holdout_season: int = None) -> dict:
    """Fit the shipped model.

    With Platt: logistic on every season before the latest full season, Platt
    on that season. Without: logistic on every season, partial current season
    included. `holdout_season` excludes that season and everything after it,
    which is how backtest.py builds a model that never saw the season it scores.
    """
    spec = MODELS[model]
    if holdout_season is not None:
        rows = [r for r in rows if r["season"] < holdout_season]
    seasons = full_seasons(rows)
    all_seasons = sorted({r["season"] for r in rows})

    if use_platt and len(seasons) >= 2:
        calib_s = seasons[-1]
        train_seasons = [s for s in all_seasons if s < calib_s]
        coefs = fit_logistic(by_seasons(rows, train_seasons), spec["columns"], spec["C"])
        calib = by_seasons(rows, [calib_s])
        calibrator = Calibrator.fit_platt(raw_probs(coefs, calib, spec["columns"]),
                                          [r["home_win"] for r in calib])
    else:
        calib_s = None
        train_seasons = all_seasons
        coefs = fit_logistic(rows, spec["columns"], spec["C"])
        calibrator = Calibrator()

    return {
        "model": model,
        "model_version": MODEL_VERSIONS[model],
        "feature_columns": spec["columns"],
        "coefficients": coefs,
        "calibrator": calibrator.to_dict(),
        "trained_on_seasons": train_seasons,
        "calibration_season": calib_s,
        "n_train_games": len(by_seasons(rows, train_seasons)),
    }


def save(artifact: dict, path: Path = WIN_MODEL_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, indent=2))


def load(path: Path = WIN_MODEL_PATH) -> dict:
    return json.loads(Path(path).read_text())


def predict(artifact: dict, features: dict) -> float:
    """Calibrated P(home win) for one game's feature dict."""
    cols = artifact["feature_columns"]
    missing = [c for c in cols if c not in features]
    if missing:
        raise ValueError(f"serving features missing {missing}")
    p = raw_prob(artifact["coefficients"], features, cols)
    return float(Calibrator.from_dict(artifact["calibrator"])([p])[0])
