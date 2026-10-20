"""
The full-data xG model: its feature sets and the fitted-model wrapper.

Lives here rather than in train_nhl_xg.py so a pickled model loads from any
script (a class pickled from __main__ only loads in that same script).
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import log_loss

# How the league logs shots drifts season to season: a shot within 3s of
# another (our rebound flag) was 4% of non-goals in 2015 and 10% by 2025, and
# shots from in tight score less often than they did. A model fitted evenly on
# 2015-2021 overstated 2023 goals by 14%. Tested on an inner split (train
# 2015-21, tune 2022, score 2023), weighting each season DECAY times the one
# after it and recalibrating on the latest season was best on log loss:
#   all seasons, raw          ll 0.22569  xG/goals 1.137
#   all seasons + Platt       ll 0.22390           1.018
#   2019-21 only + isotonic   ll 0.22178           1.004
#   decay 0.6 + isotonic      ll 0.22174           1.007
RECENCY_DECAY = 0.6

MP_NUMERIC = [
    "x_adj", "y_abs", "distance", "angle_from_net",
    "time_since_last_event", "distance_from_last_event", "speed_from_last_event",
    "prev_event_x", "prev_event_y",
    "shooting_skaters", "defending_skaters", "score_differential",
    "period", "time_seconds", "time_since_faceoff", "shooter_shift_secs",
]
MP_BINARY = ["is_rebound", "is_behind_net", "is_empty_net", "shooter_net_empty",
             "is_overtime", "off_wing", "is_home", "is_playoff", "shot_type_missing"]
MP_CATEGORICAL = ["shot_type", "situation", "period_format", "prev_event",
                  "prev_event_zone", "shooter_hand", "shooter_position"]

EXTRA_NUMERIC = ["time_since_prev2", "rebound_angle_change", "secs_since_non_oz",
                 "secs_since_won_puck", "lateral_dy", "shoot_avg_shift_secs",
                 "def_avg_shift_secs", "def_max_shift_secs", "shooter_age", "shooter_height"]
EXTRA_BINARY = ["prev_same_team", "crossed_middle"]
EXTRA_CATEGORICAL = ["rebound_from", "prev2_event"]

FEATURE_SETS = {
    "mp": (MP_NUMERIC + MP_BINARY, MP_CATEGORICAL),
    "full": (MP_NUMERIC + MP_BINARY + EXTRA_NUMERIC + EXTRA_BINARY,
             MP_CATEGORICAL + EXTRA_CATEGORICAL),
}


class XGModel:
    """A fitted booster plus the exact columns and category levels it expects,
    so scoring a new game can't silently reorder or re-code anything."""

    def __init__(self, numeric, categorical, **params):
        self.numeric, self.categorical = list(numeric), list(categorical)
        self.levels = {}
        self.params = params
        self.clf = None

    def frame(self, df):
        X = df[self.numeric].astype("float64").copy()
        for c in self.categorical:
            X[c] = pd.Categorical(df[c].astype("string").fillna("NONE"),
                                  categories=self.levels[c])
        return X

    def fit(self, train, valid, decay=RECENCY_DECAY):
        """Fit on `train`, weighted toward its latest season; stop early and
        calibrate on `valid`, which should be the season right after it."""
        for c in self.categorical:
            self.levels[c] = sorted(train[c].astype("string").fillna("NONE").unique())
        Xt, Xv = self.frame(train), self.frame(valid)
        w = decay ** (train.season.max() - train.season).to_numpy()
        # Early stopping on the validation season, not a random slice of
        # training rows: grow in steps with warm_start, keep the best count.
        clf = HistGradientBoostingClassifier(
            learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=200,
            l2_regularization=1.0, categorical_features="from_dtype",
            early_stopping=False, warm_start=True, random_state=0, **self.params)
        iters, losses, n = [], [], 0
        while n < 3000:
            n += 50
            clf.set_params(max_iter=n).fit(Xt, train.goal, sample_weight=w)
            iters.append(n)
            losses.append(log_loss(valid.goal, clf.predict_proba(Xv)[:, 1]))
            if len(losses) > 4 and min(losses[-4:]) > min(losses[:-4]):
                break
        best = iters[int(np.argmin(losses))]
        self.clf = clf.set_params(warm_start=False, max_iter=best).fit(Xt, train.goal, sample_weight=w)
        self.calibrator = IsotonicRegression(out_of_bounds="clip", y_min=1e-4, y_max=0.99).fit(
            self.raw(valid), valid.goal)
        self.trained_on = (int(train.season.min()), int(train.season.max()), int(valid.season.max()))
        return self

    def raw(self, df):
        return self.clf.predict_proba(self.frame(df))[:, 1]

    def predict(self, df):
        return self.calibrator.predict(self.raw(df))
