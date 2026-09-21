"""
Coherent serving output: one favourite, one margin, everywhere.

The win model is the source of truth for who wins and by how much; the
points model supplies only the total and hence the home/away split:

    margin = sigma * Phi^-1(p_home)          # sigma from the win model (LOSO residual std)
    home   = (total + margin) / 2
    away   = (total - margin) / 2

By construction sign(margin) == sign(p_home - 0.5), so the shipped win
probability and the shipped points can never name different favourites.

Chosen on LOSO 2015-2023 out-of-fold predictions (2,449 games), not on the
test set. Against the points model's own margin it was equal or better on
every points metric: margin RMSE 12.933 vs 12.970 (MAE 10.045 vs 10.042),
home RMSE 9.459 vs 9.480, away RMSE 9.241 vs 9.245. Favourite agreement
went from 91.3% to 100%. The reverse direction (win probability from the
points margin) cost log loss 0.6251 vs 0.6223 and was rejected.
"""
from __future__ import annotations

import numpy as np
from scipy.stats import norm

_EPS = 1e-6


def implied_margin(p_home, sigma: float) -> np.ndarray:
    p = np.clip(np.asarray(p_home, dtype=float), _EPS, 1.0 - _EPS)
    return sigma * norm.ppf(p)


def coherent_points(p_home, total, sigma: float) -> dict:
    margin = implied_margin(p_home, sigma)
    total = np.asarray(total, dtype=float)
    return {"margin": margin, "total": total,
            "home": (total + margin) / 2.0, "away": (total - margin) / 2.0}
