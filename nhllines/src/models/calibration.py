"""
Probability calibration layer (Platt / isotonic) for the shipped win model.
============================================================================
Step 4 of the rebuild roadmap: replace the hand-tuned confidence constants in
`model.py` (a stack of numbers fitted to a 35-bet sample) with a principled
calibration map fit on a *held-out season*.

Calibration is not the same thing as accuracy. A model can pick the right side
55% of the time and still be badly calibrated — its 70%-confidence bin might go
55%, its 40% bin might go 48%. Bet sizing (Kelly, EV) is driven by the *number*
p, not by which side of 0.5 it lands on, so a miscalibrated p bleeds money even
when the pick is right. This module fixes the number.

Two calibrators, both standard:
  * Platt (logistic) scaling — sigmoid(a·logit(p) + b), 2 parameters. Robust on
    small samples, but can only stretch/shift; it can't fix non-monotone kinks.
  * Isotonic regression — free-form monotone step function. More flexible,
    needs more data, can overfit on a thin calibration season.

The evaluation protocol is deliberately leak-free and mirrors the model gate's
strictness. Three disjoint, time-ordered slices:

    train the model      -> all seasons but the last two
    fit the calibrator   -> the second-to-last season   (the "held-out season")
    score calibration    -> the last season             (never seen by either)

Fitting the calibrator on the season the model was trained on would report
fantasy numbers — the model is overconfident precisely *because* it saw that
data. The calibrator must be fit on data the model did not train on, and then
judged on a third slice it also did not train on.

Adoption follows the same rule as the model gate (`model_gate.py`): a
calibration method is adopted only if it beats the uncalibrated probabilities on
BOTH log loss and Brier on the held-out test season. If neither method clears
that bar, the raw probabilities are already well enough calibrated — ship them
unchanged rather than adding a layer that only fits noise.

Usage:
    python -m src.models.calibration          # report for the shipped Elo model
    (or run the repo-root CLI: python calibrate.py)
"""

import csv
import json

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss
from sklearn.preprocessing import StandardScaler

from src.data.historical_dataset import FEATURE_COLUMNS, seasons_through_current
from src.models.elo_baseline import ELO_FEATURE_COLUMNS, build_elo_rows

# Rolling: automatically includes a new season once it starts (July 1), so
# live Elo ratings and weekly refits never freeze on a stale hardcoded list.
# Seasons with no completed games yet contribute no rows and change nothing.
DEFAULT_SEASONS = seasons_through_current("20222023")

# Probabilities are clipped away from {0, 1} before any logit / log so a single
# confident-and-wrong game can't send log loss to infinity.
_EPS = 1e-6


def _clip(p):
    return np.clip(np.asarray(p, dtype=float), _EPS, 1.0 - _EPS)


def _logit(p):
    p = _clip(p)
    return np.log(p / (1.0 - p))


# --------------------------------------------------------------------------- #
# Calibrators                                                                  #
# --------------------------------------------------------------------------- #
class IdentityCalibrator:
    """No-op: the raw model probabilities, used as the reference to beat."""

    method = "uncalibrated"

    def fit(self, p, y):
        return self

    def predict(self, p):
        return _clip(p)

    def to_dict(self):
        return {"method": self.method}

    @classmethod
    def from_dict(cls, d):
        return cls()


class PlattCalibrator:
    """Platt / logistic scaling: sigmoid(a·logit(p) + b), fit by 1-D logistic
    regression on the model's logits. Two parameters — robust on small samples,
    monotone by construction."""

    method = "platt"

    def __init__(self):
        self.a = None
        self.b = None

    def fit(self, p, y):
        z = _logit(p).reshape(-1, 1)
        lr = LogisticRegression(solver="liblinear")
        lr.fit(z, np.asarray(y, dtype=int))
        self.a = float(lr.coef_[0, 0])
        self.b = float(lr.intercept_[0])
        return self

    def predict(self, p):
        z = _logit(p)
        return _clip(1.0 / (1.0 + np.exp(-(self.a * z + self.b))))

    def to_dict(self):
        return {"method": self.method, "a": self.a, "b": self.b}

    @classmethod
    def from_dict(cls, d):
        c = cls()
        c.a, c.b = float(d["a"]), float(d["b"])
        return c


class IsotonicCalibrator:
    """Isotonic regression: free-form monotone non-decreasing map from raw p to
    calibrated p. Flexible but data-hungry; clips out-of-range inputs to the
    fitted support."""

    method = "isotonic"

    def __init__(self):
        self.iso = None

    def fit(self, p, y):
        self.iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        self.iso.fit(np.asarray(p, dtype=float), np.asarray(y, dtype=int))
        return self

    def predict(self, p):
        return _clip(self.iso.predict(np.asarray(p, dtype=float)))

    def to_dict(self):
        return {
            "method": self.method,
            "x": self.iso.X_thresholds_.tolist(),
            "y": self.iso.y_thresholds_.tolist(),
        }

    @classmethod
    def from_dict(cls, d):
        c = cls()
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        # The stored thresholds are already the monotone interpolation knots;
        # refitting on them reproduces the same piecewise-linear map exactly.
        iso.fit(np.asarray(d["x"], dtype=float), np.asarray(d["y"], dtype=float))
        c.iso = iso
        return c


CALIBRATORS = {
    IdentityCalibrator.method: IdentityCalibrator,
    PlattCalibrator.method: PlattCalibrator,
    IsotonicCalibrator.method: IsotonicCalibrator,
}


def fit_calibrator(method: str, p, y):
    if method not in CALIBRATORS:
        raise ValueError(f"Unknown calibration method: {method}")
    return CALIBRATORS[method]().fit(p, y)


def load_calibrator(d: dict):
    """Rebuild a calibrator from its to_dict() form (for persistence)."""
    return CALIBRATORS[d["method"]].from_dict(d)


# --------------------------------------------------------------------------- #
# Calibration metrics                                                          #
# --------------------------------------------------------------------------- #
def reliability_table(p, y, n_bins: int = 10) -> list:
    """Bin predictions into equal-width probability bins and report, per bin,
    the mean predicted probability vs the observed win frequency. Perfect
    calibration means mean_pred == frac_pos in every populated bin."""
    p = _clip(p)
    y = np.asarray(y, dtype=int)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    # digitize on interior edges -> bin index in [0, n_bins-1]
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, n_bins - 1)

    table = []
    for b in range(n_bins):
        mask = idx == b
        n = int(mask.sum())
        table.append({
            "bin": b,
            "lo": float(edges[b]),
            "hi": float(edges[b + 1]),
            "count": n,
            "mean_pred": float(p[mask].mean()) if n else float("nan"),
            "frac_pos": float(y[mask].mean()) if n else float("nan"),
        })
    return table


def expected_calibration_error(p, y, n_bins: int = 10) -> float:
    """ECE: count-weighted mean |mean_pred - frac_pos| across populated bins.
    Lower is better; 0 is perfect calibration."""
    p = _clip(p)
    n_total = len(p)
    if n_total == 0:
        return float("nan")
    ece = 0.0
    for row in reliability_table(p, y, n_bins):
        if row["count"]:
            ece += (row["count"] / n_total) * abs(row["mean_pred"] - row["frac_pos"])
    return ece


# --------------------------------------------------------------------------- #
# Model probability sources                                                    #
# --------------------------------------------------------------------------- #
def _load_csv_rows(path: str) -> list:
    with open(path) as f:
        return list(csv.DictReader(f))


def _fit_predict_logistic(train_rows: list, cols: list, C: float):
    """Fit a scaled logistic regression on train_rows and return a predict(rows)
    function yielding P(home_win). Matches the fitting used by the Elo baseline
    and the model gate so the raw probabilities are the same ones those ship."""
    X = np.array([[float(r[c]) for c in cols] for r in train_rows])
    y = np.array([int(r["home_win"]) for r in train_rows])
    scaler = StandardScaler().fit(X)
    model = LogisticRegression(max_iter=2000, C=C, solver="liblinear")
    model.fit(scaler.transform(X), y)

    def predict(rows: list):
        Xr = np.array([[float(r[c]) for c in cols] for r in rows])
        return model.predict_proba(scaler.transform(Xr))[:, 1]

    return predict


def _model_rows(model_name: str, seasons: list, csv_path: str):
    """Return (rows, feature_columns, C) for the requested model. `rows` each
    carry a 'season' and 'home_win' plus the model's feature columns."""
    if model_name == "elo":
        # Elo + home-ice logistic — the model the gate currently ships.
        rows = build_elo_rows(seasons, csv_path)
        return rows, ELO_FEATURE_COLUMNS, 1.0
    if model_name == "logreg":
        # 44-feature point-in-time logistic candidate (the overconfident one).
        rows = _load_csv_rows(csv_path)
        return rows, FEATURE_COLUMNS, 0.1
    raise ValueError(f"Unknown model: {model_name}")


# --------------------------------------------------------------------------- #
# Held-out-season calibration evaluation                                       #
# --------------------------------------------------------------------------- #
def evaluate_calibration(model_name: str = "elo", seasons: list = None,
                         csv_path: str = "data/training_set.csv",
                         methods=("uncalibrated", "platt", "isotonic"),
                         n_bins: int = 10) -> dict:
    """Fit the model on all-but-last-two seasons, fit each calibrator on the
    second-to-last season, and score every method on the last season. Returns
    metrics per method plus the fitted calibrators."""
    rows, cols, C = _model_rows(model_name, seasons or DEFAULT_SEASONS, csv_path)
    present = sorted(set(r["season"] for r in rows))
    if len(present) < 3:
        raise ValueError(
            "Need >= 3 seasons for leak-free calibration "
            "(train / fit calibrator / test); got: " + ", ".join(present))

    test_season = present[-1]
    calib_season = present[-2]
    train_seasons = present[:-2]

    train = [r for r in rows if r["season"] in train_seasons]
    calib = [r for r in rows if r["season"] == calib_season]
    test = [r for r in rows if r["season"] == test_season]

    predict = _fit_predict_logistic(train, cols, C)
    p_calib = predict(calib)
    y_calib = np.array([int(r["home_win"]) for r in calib])
    p_test = predict(test)
    y_test = np.array([int(r["home_win"]) for r in test])

    results = []
    for method in methods:
        cal = fit_calibrator(method, p_calib, y_calib)
        pt = cal.predict(p_test)
        results.append({
            "method": method,
            "log_loss": log_loss(y_test, pt),
            "brier": brier_score_loss(y_test, pt),
            "ece": expected_calibration_error(pt, y_test, n_bins),
            "accuracy": accuracy_score(y_test, pt > 0.5),
            "calibrator": cal,
        })

    return {
        "model": model_name,
        "train_seasons": train_seasons,
        "calib_season": calib_season,
        "test_season": test_season,
        "n_train": len(train),
        "n_calib": len(calib),
        "n_test": len(test),
        "n_bins": n_bins,
        "results": results,
        # Raw test-season probabilities + labels, so callers (the CLI report)
        # can draw a reliability table without refitting the model.
        "p_test_raw": p_test,
        "y_test": y_test,
    }


def choose_calibration(eval_result: dict):
    """Gate-style verdict: adopt the calibration method that beats the raw
    probabilities on BOTH log loss and Brier on the held-out test season; prefer
    the lower log loss when both methods pass. Returns (method_name_or_None,
    metrics_dict_of_the_chosen_or_uncalibrated)."""
    by_method = {r["method"]: r for r in eval_result["results"]}
    base = by_method["uncalibrated"]
    winners = [
        m for m in ("platt", "isotonic")
        if m in by_method
        and by_method[m]["log_loss"] < base["log_loss"]
        and by_method[m]["brier"] < base["brier"]
    ]
    if not winners:
        return None, base
    best = min(winners, key=lambda m: by_method[m]["log_loss"])
    return best, by_method[best]


def fit_production_calibrator(model_name: str = "elo", method: str = "platt",
                              seasons: list = None,
                              csv_path: str = "data/training_set.csv"):
    """Fit a calibrator for deployment: train the model on all-but-last seasons
    and fit the calibrator on the most recent complete season. Returns the
    calibrator; persist it with json.dump(cal.to_dict(), ...) and reload with
    load_calibrator(). Wire this in when the gate winner is hooked into main.py
    (roadmap step: 'wire the gate winner into main.py')."""
    rows, cols, C = _model_rows(model_name, seasons or DEFAULT_SEASONS, csv_path)
    present = sorted(set(r["season"] for r in rows))
    if len(present) < 2:
        raise ValueError("Need >= 2 seasons to fit a production calibrator")
    calib_season = present[-1]
    train = [r for r in rows if r["season"] != calib_season]
    calib = [r for r in rows if r["season"] == calib_season]
    predict = _fit_predict_logistic(train, cols, C)
    p_calib = predict(calib)
    y_calib = np.array([int(r["home_win"]) for r in calib])
    return fit_calibrator(method, p_calib, y_calib)


if __name__ == "__main__":
    result = evaluate_calibration("elo")
    print(json.dumps(
        {k: v for k, v in result.items()
         if k not in ("results", "p_test_raw", "y_test")}, indent=2))
    for r in result["results"]:
        print(f"{r['method']:<13} log_loss={r['log_loss']:.4f} "
              f"brier={r['brier']:.4f} ece={r['ece']:.4f} acc={r['accuracy']:.3f}")
