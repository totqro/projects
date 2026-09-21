"""
Leave-one-season-out (LOSO) cross-validation over the training seasons.

Every modelling choice in this project — Elo constants, feature sets, ridge
strength, calibration method, blend weights — is made by holding out each
of 2015-2023 in turn, fitting on the other eight, and scoring the held-out
season. The out-of-fold predictions are pooled for the headline number and
reported per season so a single lucky season can't carry a decision.

The 2024-2025 test seasons never enter this module.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.preprocessing import StandardScaler

from src.data.nflverse import TRAIN_SEASONS
from src.models.metrics import log_loss, brier, accuracy, ece, rmse, mae


def folds(df: pd.DataFrame, seasons=TRAIN_SEASONS):
    for s in seasons:
        yield s, df.season != s, df.season == s


class RidgeLogit:
    """Standardised-feature L2 logistic regression. `C` is sklearn's inverse
    regularisation strength (smaller = stronger shrinkage)."""

    def __init__(self, C: float = 0.1):
        self.C = C
        self.scaler = None
        self.model = None

    def fit(self, X, y):
        self.scaler = StandardScaler().fit(X)
        self.model = LogisticRegression(C=self.C, solver="lbfgs", max_iter=5000)
        self.model.fit(self.scaler.transform(X), y)
        return self

    def predict_proba(self, X):
        return self.model.predict_proba(self.scaler.transform(X))[:, 1]

    def coefficients(self, names):
        raw = self.model.coef_[0] / self.scaler.scale_
        icpt = self.model.intercept_[0] - np.sum(self.model.coef_[0] * self.scaler.mean_ / self.scaler.scale_)
        d = dict(zip(names, map(float, raw)))
        d["intercept"] = float(icpt)
        return d

    def to_dict(self, names):
        return {"type": "ridge_logit", "C": self.C, "features": list(names),
                "coef": self.coefficients(names)}


class RidgeReg:
    def __init__(self, alpha: float = 1.0):
        self.alpha = alpha
        self.scaler = None
        self.model = None

    def fit(self, X, y):
        self.scaler = StandardScaler().fit(X)
        self.model = Ridge(alpha=self.alpha).fit(self.scaler.transform(X), y)
        return self

    def predict(self, X):
        return self.model.predict(self.scaler.transform(X))

    def coefficients(self, names):
        raw = self.model.coef_ / self.scaler.scale_
        icpt = self.model.intercept_ - np.sum(self.model.coef_ * self.scaler.mean_ / self.scaler.scale_)
        d = dict(zip(names, map(float, raw)))
        d["intercept"] = float(icpt)
        return d

    def to_dict(self, names):
        return {"type": "ridge", "alpha": self.alpha, "features": list(names),
                "coef": self.coefficients(names)}


def loso_win(df: pd.DataFrame, features: list, y_col: str = "home_win", C: float = 0.1,
             seasons=TRAIN_SEASONS, weeks: tuple | None = None) -> dict:
    """Out-of-fold win probabilities from a ridge logistic on `features`.
    `weeks` optionally restricts SCORING (not fitting) to a week range, e.g.
    (1, 4) for the week-1 prior gate."""
    X = df[features].to_numpy(dtype=float)
    y = df[y_col].to_numpy(dtype=int)
    oof = np.full(len(df), np.nan)
    for s, tr, te in folds(df, seasons):
        m = RidgeLogit(C).fit(X[tr.to_numpy()], y[tr.to_numpy()])
        oof[te.to_numpy()] = m.predict_proba(X[te.to_numpy()])
    return score_oof(df, oof, y_col, seasons, weeks)


def score_oof(df: pd.DataFrame, oof: np.ndarray, y_col: str = "home_win",
              seasons=TRAIN_SEASONS, weeks: tuple | None = None) -> dict:
    y = df[y_col].to_numpy(dtype=int)
    mask = df.season.isin(seasons).to_numpy() & ~np.isnan(oof)
    if weeks is not None:
        mask &= (df.week >= weeks[0]).to_numpy() & (df.week <= weeks[1]).to_numpy()
    per = {}
    for s in seasons:
        ms = mask & (df.season == s).to_numpy()
        if ms.sum():
            per[int(s)] = {"n": int(ms.sum()), "log_loss": log_loss(y[ms], oof[ms]),
                           "brier": brier(y[ms], oof[ms]), "accuracy": accuracy(y[ms], oof[ms])}
    return {"n": int(mask.sum()), "log_loss": log_loss(y[mask], oof[mask]),
            "brier": brier(y[mask], oof[mask]), "accuracy": accuracy(y[mask], oof[mask]),
            "ece": ece(y[mask], oof[mask]), "per_season": per, "oof": oof}


def loso_reg(df: pd.DataFrame, features: list, y_col: str, alpha: float = 1.0,
             seasons=TRAIN_SEASONS) -> dict:
    X = df[features].to_numpy(dtype=float)
    y = df[y_col].to_numpy(dtype=float)
    oof = np.full(len(df), np.nan)
    for s, tr, te in folds(df, seasons):
        m = RidgeReg(alpha).fit(X[tr.to_numpy()], y[tr.to_numpy()])
        oof[te.to_numpy()] = m.predict(X[te.to_numpy()])
    mask = df.season.isin(seasons).to_numpy()
    per = {int(s): {"rmse": rmse(y[(df.season == s).to_numpy()], oof[(df.season == s).to_numpy()]),
                    "mae": mae(y[(df.season == s).to_numpy()], oof[(df.season == s).to_numpy()])}
           for s in seasons}
    return {"n": int(mask.sum()), "rmse": rmse(y[mask], oof[mask]), "mae": mae(y[mask], oof[mask]),
            "per_season": per, "oof": oof}


def beats(cand: dict, base: dict) -> dict:
    """The gate: candidate must beat baseline on BOTH log loss and Brier."""
    ll = cand["log_loss"] < base["log_loss"]
    br = cand["brier"] < base["brier"]
    return {"beats_log_loss": ll, "beats_brier": br, "passed": ll and br,
            "log_loss_gain": base["log_loss"] - cand["log_loss"],
            "brier_gain": base["brier"] - cand["brier"]}


def fmt(r: dict, label: str) -> str:
    return (f"{label:<46} n={r['n']:<5} logloss={r['log_loss']:.4f}  brier={r['brier']:.4f}  "
            f"acc={r['accuracy']:.3f}" + (f"  ece={r['ece']:.4f}" if "ece" in r else ""))
