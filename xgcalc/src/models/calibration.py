"""
Probability calibration (Platt / isotonic) for the xG model.
===========================================================

Ported from the win predictor's `nhllines/src/models/calibration.py` and kept
deliberately API-compatible with it: same three calibrator classes, same
fit/predict/to_dict/from_dict shape, same reliability/ECE helpers, same
adoption gate. If that module changes, this one should change with it.

Why an xG model needs this even when it "looks" calibrated: sum(xG)/goals can
sit at 1.00 while individual buckets are badly wrong in opposite directions
that cancel. Our five-feature model does exactly that on 2025 -- the total is
off by 7% but the top decile predicts .258 against an actual .193 while
mid-range deciles under-predict. Aggregate xG hides it; per-shot xG does not,
and anything downstream that uses a single shot's number (shot quality,
goalie save-above-expected) is driven by the number, not the total.

The evaluation protocol is the win model's, and it fits this project's
existing holdout rule exactly:

    train the model      -> 2018-2023   (all but the last two seasons)
    fit the calibrator   -> 2024        (the model has never seen it)
    score calibration    -> 2025        (neither the model nor the calibrator
                                         has seen it)

Note this does NOT violate `assert_no_holdout_leak`: the guard protects the
MODEL's training set. The calibrator is a separate two-parameter map fit on
the model's *outputs* for 2024, which is the whole point -- a calibrator fit
on data the model trained on would be fit to the model's overconfidence and
report fantasy numbers.

Adoption gate, same rule as the win model: a method is adopted only if it
beats the uncalibrated probabilities on BOTH log loss and Brier on the test
season. If neither clears the bar, ship the raw probabilities -- adding a
layer that only fits noise is worse than no layer.
"""

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss

# Probabilities are clipped away from {0, 1} before any logit / log so a single
# confident-and-wrong shot can't send log loss to infinity.
_EPS = 1e-6


def _clip(p):
    return np.clip(np.asarray(p, dtype=float), _EPS, 1.0 - _EPS)


def _logit(p):
    p = _clip(p)
    return np.log(p / (1.0 - p))


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
    monotone by construction, so it can stretch and shift but cannot invent a
    non-monotone kink."""

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
    fitted support. With ~120k shots per season there is far more data here
    than the win model's ~1,300 games, so isotonic is a live option rather
    than an automatic overfit."""

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
        return {"method": self.method,
                "x": self.iso.X_thresholds_.tolist(),
                "y": self.iso.y_thresholds_.tolist()}

    @classmethod
    def from_dict(cls, d):
        c = cls()
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
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


def reliability_table(p, y, n_bins: int = 10) -> list:
    """Per equal-width probability bin: mean predicted vs observed frequency.
    Perfect calibration means mean_pred == frac_pos in every populated bin."""
    p = _clip(p)
    y = np.asarray(y, dtype=int)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, n_bins - 1)
    table = []
    for b in range(n_bins):
        mask = idx == b
        n = int(mask.sum())
        table.append({"bin": b, "lo": float(edges[b]), "hi": float(edges[b + 1]),
                      "count": n,
                      "mean_pred": float(p[mask].mean()) if n else float("nan"),
                      "frac_pos": float(y[mask].mean()) if n else float("nan")})
    return table


def expected_calibration_error(p, y, n_bins: int = 10) -> float:
    """ECE: count-weighted mean |mean_pred - frac_pos| across populated bins."""
    p = _clip(p)
    if len(p) == 0:
        return float("nan")
    ece = 0.0
    for row in reliability_table(p, y, n_bins):
        if row["count"]:
            ece += (row["count"] / len(p)) * abs(row["mean_pred"] - row["frac_pos"])
    return ece


def choose_calibration(metrics_by_method: dict):
    """Gate-style verdict, same rule as the win model: adopt the method that
    beats raw probabilities on BOTH log loss and Brier; prefer lower log loss
    when both pass. Returns (method_or_None, chosen_metrics)."""
    base = metrics_by_method["uncalibrated"]
    winners = [m for m in ("platt", "isotonic")
               if m in metrics_by_method
               and metrics_by_method[m]["log_loss"] < base["log_loss"]
               and metrics_by_method[m]["brier"] < base["brier"]]
    if not winners:
        return None, base
    best = min(winners, key=lambda m: metrics_by_method[m]["log_loss"])
    return best, metrics_by_method[best]


def score(p, y, n_bins: int = 10) -> dict:
    y = np.asarray(y, dtype=int)
    p = _clip(p)
    return {"log_loss": log_loss(y, p, labels=[0, 1]),
            "brier": brier_score_loss(y, p),
            "ece": expected_calibration_error(p, y, n_bins),
            "sum_ratio": float(p.sum() / y.sum())}
