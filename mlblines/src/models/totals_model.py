"""
MLB expected total runs: gated against a league-average baseline.
=================================================================
Baseline: every game gets the training seasons' average total. One parameter.
Candidate: a Poisson GLM (log link) on starters, bullpens, team run rates,
park factor and the season-to-date league scoring level
(historical_dataset.TOTALS_FEATURE_COLUMNS).

The candidate ships only if it beats the baseline on BOTH held-out RMSE and
mean negative log-likelihood. Totals are overdispersed relative to Poisson, so
the likelihood is a negative binomial whose dispersion is fit on the training
seasons, and the same distribution turns an expected total into P(over line).
"""

import json
import math
from pathlib import Path

import numpy as np
from scipy.special import gammaln
from sklearn.linear_model import PoissonRegressor
from sklearn.preprocessing import StandardScaler

from src.data.historical_dataset import TOTALS_FEATURE_COLUMNS
from src.models.win_model import by_seasons, full_seasons

TOTALS_MODEL_PATH = Path(__file__).resolve().parents[2] / "ml_models" / "totals_model.json"
MODEL_VERSIONS = {"glm": "mlb-totals-nbglm-v1", "baseline": "mlb-totals-leagueavg-v1"}


# --------------------------------------------------------------------------- #
# Distribution helpers                                                         #
# --------------------------------------------------------------------------- #
def fit_dispersion(y, mu) -> float:
    """Method-of-moments NB size r from Var = mu + mu^2 / r."""
    y, mu = np.asarray(y, float), np.asarray(mu, float)
    excess = np.mean((y - mu) ** 2 - mu)
    if excess <= 0:
        return 1e6  # no overdispersion: effectively Poisson
    return float(np.mean(mu ** 2) / excess)


def nb_nll(y, mu, r: float) -> float:
    y, mu = np.asarray(y, float), np.clip(np.asarray(mu, float), 1e-6, None)
    ll = (gammaln(y + r) - gammaln(r) - gammaln(y + 1)
          + r * np.log(r / (r + mu)) + y * np.log(mu / (r + mu)))
    return float(-np.mean(ll))


def nb_pmf(k: int, mu: float, r: float) -> float:
    return math.exp(gammaln(k + r) - gammaln(r) - gammaln(k + 1)
                    + r * math.log(r / (r + mu)) + k * math.log(mu / (r + mu)))


def over_probability(mu: float, line: float, r: float) -> float:
    """P(total > line); a push on a whole-number line counts as half."""
    floor = int(math.floor(line))
    cdf = sum(nb_pmf(k, mu, r) for k in range(floor + 1))
    if line != floor:
        return max(0.0, min(1.0, 1.0 - cdf))
    return max(0.0, min(1.0, 1.0 - cdf + 0.5 * nb_pmf(floor, mu, r)))


def totals_metrics(pred, actual, r: float) -> dict:
    pred, actual = np.asarray(pred, float), np.asarray(actual, float)
    if len(actual) == 0:
        return {"n": 0}
    return {
        "n": int(len(actual)),
        "rmse": float(np.sqrt(np.mean((pred - actual) ** 2))),
        "mae": float(np.mean(np.abs(pred - actual))),
        "nb_nll": nb_nll(actual, pred, r),
    }


# --------------------------------------------------------------------------- #
# Fitting                                                                      #
# --------------------------------------------------------------------------- #
def fit_glm(rows: list) -> dict:
    X = np.array([[float(r[c]) for c in TOTALS_FEATURE_COLUMNS] for r in rows])
    y = np.array([float(r["total_runs"]) for r in rows])
    scaler = StandardScaler().fit(X)
    model = PoissonRegressor(alpha=1e-3, max_iter=1000)
    model.fit(scaler.transform(X), y)
    raw = model.coef_ / scaler.scale_
    intercept = model.intercept_ - float(np.sum(model.coef_ * scaler.mean_ / scaler.scale_))
    coefs = dict(zip(TOTALS_FEATURE_COLUMNS, (float(v) for v in raw)))
    coefs["intercept"] = float(intercept)
    mu = np.array([glm_mean(coefs, r) for r in rows])
    return {"coefficients": coefs, "dispersion": fit_dispersion(y, mu)}


def glm_mean(coefs: dict, features: dict) -> float:
    return math.exp(coefs["intercept"] + sum(coefs[c] * float(features[c])
                                             for c in TOTALS_FEATURE_COLUMNS))


def fit_baseline(rows: list) -> dict:
    y = np.array([float(r["total_runs"]) for r in rows])
    mean = float(y.mean())
    return {"mean": mean, "dispersion": fit_dispersion(y, np.full(len(y), mean))}


# --------------------------------------------------------------------------- #
# Gate                                                                         #
# --------------------------------------------------------------------------- #
def evaluate_split(rows: list, test_season: int, train_seasons: list) -> dict:
    train, test = by_seasons(rows, train_seasons), by_seasons(rows, [test_season])
    actual = [r["total_runs"] for r in test]
    base = fit_baseline(train)
    glm = fit_glm(train)
    base_m = totals_metrics([base["mean"]] * len(test), actual, base["dispersion"])
    glm_m = totals_metrics([glm_mean(glm["coefficients"], r) for r in test], actual, glm["dispersion"])
    return {
        "test_season": test_season, "train_seasons": train_seasons,
        "baseline": base_m, "glm": glm_m,
        "glm_beats_baseline": glm_m["rmse"] < base_m["rmse"] and glm_m["nb_nll"] < base_m["nb_nll"],
    }


def run_gate(rows: list) -> dict:
    seasons = full_seasons(rows)
    test = seasons[-1]
    primary = evaluate_split(rows, test, [s for s in seasons if s < test])
    loso = [evaluate_split(rows, s, [x for x in seasons if x != s]) for s in seasons]
    return {
        "primary": primary,
        "loso": loso,
        "loso_glm_wins": sum(1 for r in loso if r["glm_beats_baseline"]),
        "passed": primary["glm_beats_baseline"],
        "winner": "glm" if primary["glm_beats_baseline"] else "baseline",
    }


def fit_production(rows: list, model: str, holdout_season: int = None) -> dict:
    if holdout_season is not None:
        rows = [r for r in rows if r["season"] < holdout_season]
    seasons = sorted({r["season"] for r in rows})
    artifact = {"model": model, "model_version": MODEL_VERSIONS[model],
                "trained_on_seasons": seasons, "n_train_games": len(rows)}
    artifact.update(fit_glm(rows) if model == "glm" else fit_baseline(rows))
    if model == "glm":
        artifact["feature_columns"] = TOTALS_FEATURE_COLUMNS
    return artifact


def save(artifact: dict, path: Path = TOTALS_MODEL_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, indent=2))


def load(path: Path = TOTALS_MODEL_PATH) -> dict:
    return json.loads(Path(path).read_text())


def predict(artifact: dict, features: dict) -> float:
    if artifact["model"] == "glm":
        return glm_mean(artifact["coefficients"], features)
    return artifact["mean"]
