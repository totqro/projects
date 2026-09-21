"""
The win model: ridge logistic on a small feature set, optionally blended
with a Normal win probability derived from a ridge margin regression.

    p_logit  = sigmoid(w . x)                         (direct win model)
    p_margin = Phi(mu_margin / sigma)                 (margin -> win)
    p        = (1 - blend) * p_logit + blend * p_margin

`sigma` is the std of the margin regression's LOSO residuals on the training
seasons. Everything here is fit on the rows it is given; the gate
(model_gate.py) decides the feature list, C, alpha and blend by LOSO and
writes them to ml_models/win_model.json, which `load()` reads back for
serving and for evaluate_test.py.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

from src.models.loso import RidgeLogit, RidgeReg

MODEL_DIR = Path(__file__).resolve().parents[2] / "ml_models"
WIN_MODEL_PATH = MODEL_DIR / "win_model.json"
POINTS_MODEL_PATH = MODEL_DIR / "points_model.json"


class WinModel:
    def __init__(self, features: list, C: float = 0.1, margin_features: list | None = None,
                 alpha: float = 1.0, blend: float = 0.0, sigma: float = 13.5):
        self.features = list(features)
        self.C = C
        self.margin_features = list(margin_features or features)
        self.alpha = alpha
        self.blend = blend
        self.sigma = sigma
        self.logit = None
        self.margin = None
        self.calibrator = None

    def fit(self, df: pd.DataFrame):
        d = df[df.home_win.notna()]
        self.logit = RidgeLogit(self.C).fit(d[self.features].to_numpy(float), d.home_win.to_numpy(int))
        if self.blend > 0:
            self.margin = RidgeReg(self.alpha).fit(df[self.margin_features].to_numpy(float), df.margin.to_numpy(float))
        return self

    def predict_margin(self, df: pd.DataFrame) -> np.ndarray:
        if self.margin is None:
            raise RuntimeError("no margin model fitted")
        return self.margin.predict(df[self.margin_features].to_numpy(float))

    def predict_proba(self, df: pd.DataFrame, calibrated: bool = True) -> np.ndarray:
        p = self.logit.predict_proba(df[self.features].to_numpy(float))
        if self.blend > 0:
            pm = norm.cdf(self.predict_margin(df) / self.sigma)
            p = (1 - self.blend) * p + self.blend * pm
        if calibrated and self.calibrator is not None:
            p = self.calibrator.predict(p)
        return p

    def to_dict(self) -> dict:
        d = {"features": self.features, "C": self.C, "margin_features": self.margin_features,
             "alpha": self.alpha, "blend": self.blend, "sigma": self.sigma,
             "logit": self.logit.to_dict(self.features) if self.logit else None,
             "margin": self.margin.to_dict(self.margin_features) if self.margin else None,
             "calibrator": self.calibrator.to_dict() if self.calibrator else None}
        return d

    def save(self, path: Path = WIN_MODEL_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=1)

    @classmethod
    def load(cls, path: Path = WIN_MODEL_PATH, df: pd.DataFrame | None = None):
        """Rebuild from JSON. The sklearn objects are refit from `df` (the
        training rows) — the JSON is the record of what was chosen."""
        with open(path) as f:
            d = json.load(f)
        m = cls(d["features"], d["C"], d["margin_features"], d["alpha"], d["blend"], d["sigma"])
        if df is not None:
            m.fit(df)
        if d.get("calibrator"):
            from src.models.calibration import load_calibrator
            m.calibrator = load_calibrator(d["calibrator"])
        return m


# --------------------------------------------------------------------------- #
# Serving from the persisted coefficients (no training data needed)           #
# --------------------------------------------------------------------------- #
class _Linear:
    """x . coef + intercept, from a raw-unit coefficient dict as written by
    RidgeLogit/RidgeReg.to_dict(). Mathematically identical to the fitted
    sklearn model (the standardisation is folded into the coefficients)."""

    def __init__(self, coef: dict, features: list):
        self.features = list(features)
        self.w = np.array([coef[f] for f in self.features], dtype=float)
        self.b = float(coef["intercept"])

    def __call__(self, df: pd.DataFrame) -> np.ndarray:
        return df[self.features].to_numpy(float) @ self.w + self.b


class ServedWinModel:
    """The shipped win model rebuilt from ml_models/win_model.json alone.
    This is what predict.py (and the GitHub Actions job) serves; it needs no
    feature table, so CI never rebuilds or refits anything."""

    def __init__(self, path: Path = WIN_MODEL_PATH):
        with open(path) as f:
            d = json.load(f)
        self.spec = d
        self.sigma = float(d["sigma"])
        self.blend = float(d["blend"])
        self._logit = _Linear(d["logit"]["coef"], d["features"])
        self._margin = _Linear(d["margin"]["coef"], d["margin_features"]) if d.get("margin") else None
        self.calibrator = None
        if d.get("calibrator"):
            from src.models.calibration import load_calibrator
            self.calibrator = load_calibrator(d["calibrator"])

    def predict_margin(self, df: pd.DataFrame) -> np.ndarray:
        return self._margin(df)

    def predict_proba(self, df: pd.DataFrame, calibrated: bool = True) -> np.ndarray:
        p = 1.0 / (1.0 + np.exp(-self._logit(df)))
        if self.blend > 0:
            p = (1 - self.blend) * p + self.blend * norm.cdf(self.predict_margin(df) / self.sigma)
        if calibrated and self.calibrator is not None:
            p = self.calibrator.predict(p)
        return p
