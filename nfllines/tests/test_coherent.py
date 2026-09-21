"""Shipped win probability and shipped margin always name the same favourite."""
import numpy as np

from src.models.coherent import coherent_points


def test_favourite_always_agrees():
    rng = np.random.default_rng(0)
    p = rng.uniform(0.01, 0.99, 5000)
    out = coherent_points(p, rng.uniform(30, 60, 5000), sigma=12.94)
    assert np.all((p > 0.5) == (out["margin"] > 0))
    assert np.allclose(out["home"] - out["away"], out["margin"])
    assert np.allclose(out["home"] + out["away"], out["total"])


def test_coin_flip_is_zero_margin():
    out = coherent_points([0.5], [44.0], sigma=12.94)
    assert abs(out["margin"][0]) < 1e-9 and out["home"][0] == out["away"][0] == 22.0
