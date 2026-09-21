"""Hard rule 4: point-in-time features, one code path for history and serving.

1. Recomputation equality: a fresh engine walked over only the weeks before
   a random game reproduces its stored feature row exactly (the same check
   build_dataset.py --verify runs; here on a smaller sample).
2. Future-blindness: perturbing the SCORES of every game after week w leaves
   the features of week-w games untouched.
"""
import numpy as np
import pandas as pd
import pytest

from src.data import nflverse as nv
from src.features.build import build_features, feature_columns, load_inputs, serve_features

SEASONS = (2014, 2015, 2016)


@pytest.fixture(scope="module")
def built():
    inputs = load_inputs(SEASONS)
    df, _ = build_features(inputs=inputs)
    return df, inputs


def _assert_rows_equal(stored, fresh, cols):
    for c in cols:
        a, b = stored[c], fresh[c]
        if isinstance(a, str):
            assert a == b, c
        else:
            assert np.isclose(float(a), float(b), rtol=0, atol=0) or (np.isnan(float(a)) and np.isnan(float(b))), (c, a, b)


def test_recompute_random_games(built):
    df, inputs = built
    cols = feature_columns(df)
    rng = np.random.default_rng(7)
    for gid in rng.choice(df[df.season >= 2015].game_id.to_numpy(), 6, replace=False):
        stored = df[df.game_id == gid].iloc[0]
        fresh = serve_features(inputs, gid)
        _assert_rows_equal(stored, fresh, cols)


def test_features_blind_to_future_results(built):
    df, inputs = built
    cols = feature_columns(df)
    season, week = 2016, 9
    g = inputs["games"]
    rng = np.random.default_rng(3)
    later = (g.season > season) | ((g.season == season) & (g.week > week))
    poisoned = dict(inputs)
    pg = g.copy()
    pg.loc[later, "home_score"] = rng.integers(0, 60, later.sum()).astype(float)
    pg.loc[later, "away_score"] = rng.integers(0, 60, later.sum()).astype(float)
    poisoned["games"] = pg
    from src.data.team_games import build_team_games, build_qb_games
    poisoned["team_games"] = build_team_games(pg[pg.home_score.notna()])
    poisoned["qb_games"] = build_qb_games(pg[pg.home_score.notna()])
    dirty, _ = build_features(inputs=poisoned)
    m = (df.season == season) & (df.week == week)
    a, b = df[m].set_index("game_id"), dirty[m.to_numpy()].set_index("game_id")
    for gid in a.index:
        _assert_rows_equal(a.loc[gid], b.loc[gid], cols)
