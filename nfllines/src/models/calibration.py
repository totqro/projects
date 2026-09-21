"""Platt / isotonic calibrators (mirrors nhllines/src/models/calibration.py)."""
from __future__ import annotations

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from src.models.metrics import clip


def _logit(p):
    p = clip(p)
    return np.log(p / (1.0 - p))


class IdentityCalibrator:
    method = "uncalibrated"

    def fit(self, p, y):
        return self

    def predict(self, p):
        return clip(p)

    def to_dict(self):
        return {"method": self.method}

    @classmethod
    def from_dict(cls, d):
        return cls()


class PlattCalibrator:
    method = "platt"

    def __init__(self):
        self.a = None
        self.b = None

    def fit(self, p, y):
        lr = LogisticRegression(solver="lbfgs", C=1e6, max_iter=5000)
        lr.fit(_logit(p).reshape(-1, 1), np.asarray(y, dtype=int))
        self.a, self.b = float(lr.coef_[0, 0]), float(lr.intercept_[0])
        return self

    def predict(self, p):
        return clip(1.0 / (1.0 + np.exp(-(self.a * _logit(p) + self.b))))

    def to_dict(self):
        return {"method": self.method, "a": self.a, "b": self.b}

    @classmethod
    def from_dict(cls, d):
        c = cls()
        c.a, c.b = float(d["a"]), float(d["b"])
        return c


class IsotonicCalibrator:
    method = "isotonic"

    def __init__(self):
        self.iso = None

    def fit(self, p, y):
        self.iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        self.iso.fit(np.asarray(p, dtype=float), np.asarray(y, dtype=int))
        return self

    def predict(self, p):
        return clip(self.iso.predict(np.asarray(p, dtype=float)))

    def to_dict(self):
        return {"method": self.method, "x": self.iso.X_thresholds_.tolist(), "y": self.iso.y_thresholds_.tolist()}

    @classmethod
    def from_dict(cls, d):
        c = cls()
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        iso.fit(np.asarray(d["x"], dtype=float), np.asarray(d["y"], dtype=float))
        c.iso = iso
        return c


CALIBRATORS = {c.method: c for c in (IdentityCalibrator, PlattCalibrator, IsotonicCalibrator)}


def fit_calibrator(method: str, p, y):
    return CALIBRATORS[method]().fit(p, y)


def load_calibrator(d: dict):
    return CALIBRATORS[d["method"]].from_dict(d)
