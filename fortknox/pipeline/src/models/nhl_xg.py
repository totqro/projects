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
# That split was too short to see further. Scored walk-forward instead
# (xg_lab.py, Nov 2026: season S trained on .. S-2, calibrated on S-1, for
# 2023-2026), a grid of decay x training window showed the decay is what
# matters. Pooled log loss, every season kept:
#   decay 0.6  0.22103   0.4  0.22017   0.3  0.21986   0.2  0.21959   0.1  0.21957
# Every decay <= 0.3 with any window (last 2, 3, 4 seasons or all) landed
# within 0.00025 of the best (0.1, last 3: 0.21940); with seasons weighted
# down this hard, dropping the old ones changes nothing. One season alone
# scored 0.21964. 0.2 also took power-play xG/goals from 1.064 to 1.044.
RECENCY_DECAY = 0.2

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


# One calibration curve for every shot left the strengths off in opposite
# directions: scored walk-forward (xg_lab.py), 5v5 xG came out 2-3% under
# 5v5 goals and power-play xG 4-6% over, which the site's 5v5 and PP rates
# inherit. So each of these groups gets its own curve.
STRENGTH_GROUPS = ("5v5", "pp", "other")


def strength_group(situation):
    """The calibration group of each shot's `situation`, as an array."""
    s = pd.Series(situation).astype("string")
    return np.where(s == "EV_5v5", "5v5", np.where(s.str.startswith("PP").fillna(False), "pp", "other"))


# The served model is calibrated once, on the last complete season, so a
# season that scores more or less than that one is off all year (2025-26 ran
# xG/goals 1.056, 2026-27 0.97 by late November). The season's own games
# correct it: before each date, each strength group's odds are scaled by
# (goals + k) / (xG + k) over that group's shots on earlier dates. k is the
# goals of evidence it takes to move halfway, 300 split by each group's share
# of goals. Scored walk-forward on 2023-2026 (experiments/xg_inseason.py):
#   pooled xG/goals 1.018 -> 1.005, 5v5 1.010 -> 1.003, PP 1.040 -> 1.001,
#   2025-26 1.056 -> 1.020, log loss unchanged (0.21993 -> 0.21990).
# A shot only ever sees earlier dates, so a game's xG doesn't move once its
# date has passed, and a season starts at the served calibration.
INSEASON_K = {"5v5": 200.0, "pp": 60.0, "other": 40.0}


def inseason_table(dates, goal, xg, group):
    """Cumulative goals and model xG per strength group through the end of
    each date: {"dates": [...], "goals": {g: [...]}, "xg": {g: [...]}}."""
    t = pd.DataFrame({"d": np.asarray(dates, dtype=str), "g": np.asarray(group),
                      "y": np.asarray(goal, dtype=float), "p": np.asarray(xg, dtype=float)})
    days = sorted(t.d.unique())
    out = {"dates": days, "goals": {}, "xg": {}}
    for g in STRENGTH_GROUPS:
        s = t[t.g == g].groupby("d")[["y", "p"]].sum().reindex(days, fill_value=0.0).cumsum()
        out["goals"][g] = [round(float(v), 4) for v in s.y]
        out["xg"][g] = [round(float(v), 4) for v in s.p]
    return out


def inseason_adjust(xg, dates, group, table, k=INSEASON_K):
    """Each shot's xG with its group's odds scaled by the season so far:
    the totals of `table` through the last date before the shot's."""
    xg = np.asarray(xg, dtype=float)
    dates, group = np.asarray(dates, dtype=str), np.asarray(group)
    days = np.asarray(table["dates"], dtype=str)
    i = np.searchsorted(days, dates, side="left") - 1     # last date strictly before
    out = xg.copy()
    for g in STRENGTH_GROUPS:
        m = group == g
        if not m.any():
            continue
        G = np.r_[0.0, table["goals"][g]][i[m] + 1]
        X = np.r_[0.0, table["xg"][g]][i[m] + 1]
        r = (G + k[g]) / (X + k[g])
        p = xg[m]
        out[m] = p * r / (1 - p + p * r)
    return out


def _isotonic(raw, goal):
    return IsotonicRegression(out_of_bounds="clip", y_min=1e-4, y_max=0.99).fit(raw, goal)


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

    def fit(self, train, valid, decay=RECENCY_DECAY, calibration="strength"):
        """Fit on `train`, weighted toward its latest season; stop early and
        calibrate on `valid`, which should be the season right after it.
        calibration: "strength" (a curve per STRENGTH_GROUPS), "global" (one
        curve) or None (leave it to the caller: xg_lab.py)."""
        for c in self.categorical:
            self.levels[c] = sorted(train[c].astype("string").fillna("NONE").unique())
        Xt, Xv = self.frame(train), self.frame(valid)
        w = decay ** (train.season.max() - train.season).to_numpy()
        # Early stopping on the validation season, not a random slice of
        # training rows: grow in steps with warm_start, keep the best count.
        kw = dict(learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=200, l2_regularization=1.0)
        kw.update(self.params)
        clf = HistGradientBoostingClassifier(
            categorical_features="from_dtype", early_stopping=False, warm_start=True,
            random_state=0, **kw)
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
        if calibration:
            self.calibration = self.fit_calibration(
                self.raw(valid), valid.goal.to_numpy(), strength_group(valid.situation), calibration)
        self.trained_on = (int(train.season.min()), int(train.season.max()), int(valid.season.max()))
        return self

    @staticmethod
    def fit_calibration(raw, goal, group, how):
        """{group: isotonic curve}; "all" is the curve for every shot, used
        alone when how == "global" and for any group not fitted."""
        cal = {"all": _isotonic(raw, goal)}
        if how == "strength":
            for g in STRENGTH_GROUPS:
                m = group == g
                if m.sum() >= 2000:
                    cal[g] = _isotonic(raw[m], goal[m])
        return cal

    @staticmethod
    def apply_calibration(cal, raw, group):
        p = cal["all"].predict(raw)
        for g, iso in cal.items():
            if g != "all":
                m = group == g
                p[m] = iso.predict(raw[m])
        return p

    def raw(self, df):
        return self.clf.predict_proba(self.frame(df))[:, 1]

    def predict(self, df):
        if not hasattr(self, "calibration"):   # a model saved before the per-strength curves
            return self.calibrator.predict(self.raw(df))
        return self.apply_calibration(self.calibration, self.raw(df), strength_group(df.situation))
