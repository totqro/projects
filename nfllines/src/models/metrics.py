"""Proper scoring rules, calibration diagnostics and bootstrap CIs shared by
the gate, the calibration report and the one-time test evaluation. One
definition of each metric so 'beat the baseline' and 'scored X on the test
set' mean the same thing."""
from __future__ import annotations

import numpy as np

_EPS = 1e-6


def clip(p):
    return np.clip(np.asarray(p, dtype=float), _EPS, 1.0 - _EPS)


def log_loss(y, p) -> float:
    y = np.asarray(y, dtype=float)
    p = clip(p)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def brier(y, p) -> float:
    y = np.asarray(y, dtype=float)
    return float(np.mean((clip(p) - y) ** 2))


def accuracy(y, p) -> float:
    y = np.asarray(y, dtype=float)
    return float(np.mean((np.asarray(p) > 0.5) == (y == 1)))


def reliability_table(y, p, n_bins: int = 10) -> list:
    y = np.asarray(y, dtype=float)
    p = clip(p)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, n_bins - 1)
    table = []
    for b in range(n_bins):
        mask = idx == b
        n = int(mask.sum())
        table.append({
            "bin": f"{edges[b]:.1f}-{edges[b + 1]:.1f}",
            "n": n,
            "mean_pred": float(p[mask].mean()) if n else float("nan"),
            "frac_pos": float(y[mask].mean()) if n else float("nan"),
        })
    return table


def ece(y, p, n_bins: int = 10) -> float:
    table = reliability_table(y, p, n_bins)
    n = sum(r["n"] for r in table)
    return float(sum(r["n"] / n * abs(r["mean_pred"] - r["frac_pos"]) for r in table if r["n"]))


def rmse(y, yhat) -> float:
    y = np.asarray(y, dtype=float); yhat = np.asarray(yhat, dtype=float)
    return float(np.sqrt(np.mean((y - yhat) ** 2)))


def mae(y, yhat) -> float:
    y = np.asarray(y, dtype=float); yhat = np.asarray(yhat, dtype=float)
    return float(np.mean(np.abs(y - yhat)))


def win_metrics(y, p) -> dict:
    return {"n": int(len(y)), "log_loss": log_loss(y, p), "brier": brier(y, p),
            "accuracy": accuracy(y, p), "ece": ece(y, p)}


def bootstrap_gap(y, p_a, p_b, metric=log_loss, n_boot: int = 2000, seed: int = 0) -> dict:
    """Paired bootstrap of metric(a) - metric(b) over games. Negative means
    `a` is better (lower loss). Returns point estimate and a 95% interval."""
    rng = np.random.default_rng(seed)
    y = np.asarray(y); p_a = np.asarray(p_a); p_b = np.asarray(p_b)
    n = len(y)
    gaps = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, n)
        gaps[i] = metric(y[idx], p_a[idx]) - metric(y[idx], p_b[idx])
    point = metric(y, p_a) - metric(y, p_b)
    lo, hi = np.percentile(gaps, [2.5, 97.5])
    return {"gap": float(point), "ci_lo": float(lo), "ci_hi": float(hi),
            "within_noise": bool(lo <= 0.0 <= hi)}
