"""
Points model (secondary goal): expected points for each team in a game.

Two rows per game (home, away). Each row's features are the team's own
offensive ratings, the opponent's defensive ratings, the team's starting QB
rating, venue/rest/weather, and both sides' injury adjustments. Ridge
regression; alpha by LOSO. Margin = home - away, total = home + away.

Baseline to beat: league-average points per team (training mean) with a
home adjustment (half the mean home margin), which is what a model with no
information about the teams would say. Gate: LOSO RMSE AND MAE for team
points, margin and total.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.data.nflverse import TRAIN_SEASONS
from src.models.loso import RidgeReg, folds
from src.models.metrics import rmse, mae

OWN_OFF = ["epa", "pass_epa", "rush_epa", "success", "explosive", "points", "plays", "pass_share", "sack_rate", "int_rate"]
OPP_DEF = ["epa", "pass_epa", "rush_epa", "success", "explosive", "points", "plays", "sack_rate", "int_rate"]
TEAM_FEATURES = ([f"own_off_{s}" for s in OWN_OFF] + [f"opp_def_{s}" for s in OPP_DEF]
                 + ["is_home", "neutral", "own_qb_epa", "opp_qb_epa", "elo_diff_own", "own_rest", "opp_rest",
                    "dome", "wind", "temp", "own_inj", "opp_inj", "season_idx", "playoff"])
INJ_GROUPS = ["RB", "WR", "TE", "OL", "DL", "LB", "DB"]


def team_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Reshape the game-level feature table into two team-game rows per game."""
    out = []
    for side, opp in (("home", "away"), ("away", "home")):
        r = pd.DataFrame({"game_id": df.game_id, "season": df.season, "week": df.week, "side": side,
                          "points": df[f"{side}_score"]})
        for s in OWN_OFF:
            r[f"own_off_{s}"] = df[f"{side}_off_{s}"]
        for s in OPP_DEF:
            r[f"opp_def_{s}"] = df[f"{opp}_def_{s}"]
        r["is_home"] = (1.0 - df.neutral) if side == "home" else 0.0
        r["neutral"] = df.neutral
        r["own_qb_epa"] = df[f"{side}_qb_epa"]
        r["opp_qb_epa"] = df[f"{opp}_qb_epa"]
        r["elo_diff_own"] = df.elo_diff if side == "home" else -df.elo_diff
        r["own_rest"] = df[f"{side}_rest"]
        r["opp_rest"] = df[f"{opp}_rest"]
        for c in ("dome", "wind", "temp", "season_idx", "playoff"):
            r[c] = df[c]
        r["own_inj"] = sum(df[f"{side}_inj_{g}"] for g in INJ_GROUPS)
        r["opp_inj"] = sum(df[f"{opp}_inj_{g}"] for g in INJ_GROUPS)
        out.append(r)
    return pd.concat(out, ignore_index=True)


def _game_level(rows: pd.DataFrame, pred: np.ndarray, df: pd.DataFrame) -> pd.DataFrame:
    r = rows.assign(pred=pred)
    h = r[r.side == "home"].set_index("game_id").pred
    a = r[r.side == "away"].set_index("game_id").pred
    g = df.set_index("game_id")[["season", "week", "home_score", "away_score", "margin", "total"]].copy()
    g["pred_home"] = h.reindex(g.index)
    g["pred_away"] = a.reindex(g.index)
    g["pred_margin"] = g.pred_home - g.pred_away
    g["pred_total"] = g.pred_home + g.pred_away
    return g


def score_game_level(g: pd.DataFrame) -> dict:
    return {
        "home_rmse": rmse(g.home_score, g.pred_home), "home_mae": mae(g.home_score, g.pred_home),
        "away_rmse": rmse(g.away_score, g.pred_away), "away_mae": mae(g.away_score, g.pred_away),
        "margin_rmse": rmse(g.margin, g.pred_margin), "margin_mae": mae(g.margin, g.pred_margin),
        "total_rmse": rmse(g.total, g.pred_total), "total_mae": mae(g.total, g.pred_total),
        "n": int(len(g)),
    }


def loso_points(df: pd.DataFrame, features: list = TEAM_FEATURES, alpha: float = 10.0,
                seasons=TRAIN_SEASONS) -> dict:
    rows = team_rows(df)
    X = rows[features].to_numpy(float)
    y = rows.points.to_numpy(float)
    oof = np.full(len(rows), np.nan)
    for s, tr, te in folds(rows, seasons):
        m = RidgeReg(alpha).fit(X[tr.to_numpy()], y[tr.to_numpy()])
        oof[te.to_numpy()] = m.predict(X[te.to_numpy()])
    g = _game_level(rows, oof, df)
    g = g[g.season.isin(seasons)]
    res = score_game_level(g)
    res["game_level"] = g
    return res


def loso_baseline(df: pd.DataFrame, seasons=TRAIN_SEASONS) -> dict:
    """League-average points per team + home adjustment, fit per fold."""
    g = df.set_index("game_id")[["season", "week", "home_score", "away_score", "margin", "total", "neutral"]].copy()
    g["pred_home"] = np.nan
    g["pred_away"] = np.nan
    for s, tr, te in folds(df, seasons):
        trn = df[tr]
        avg = (trn.home_score.mean() + trn.away_score.mean()) / 2
        hadj = trn.loc[trn.neutral == 0, "margin"].mean() / 2
        te_ids = df[te].game_id
        g.loc[te_ids, "pred_home"] = avg + hadj * (1 - g.loc[te_ids, "neutral"])
        g.loc[te_ids, "pred_away"] = avg - hadj * (1 - g.loc[te_ids, "neutral"])
    g["pred_margin"] = g.pred_home - g.pred_away
    g["pred_total"] = g.pred_home + g.pred_away
    g = g[g.season.isin(seasons)]
    res = score_game_level(g)
    res["game_level"] = g
    return res


def beats_points(cand: dict, base: dict) -> dict:
    keys = ["home", "away", "margin", "total"]
    out = {}
    for k in keys:
        out[k] = bool(cand[f"{k}_rmse"] < base[f"{k}_rmse"] and cand[f"{k}_mae"] < base[f"{k}_mae"])
    out["passed"] = all(out[k] for k in keys)
    return out


class PointsModel:
    def __init__(self, features: list = TEAM_FEATURES, alpha: float = 10.0):
        self.features = list(features)
        self.alpha = alpha
        self.model = None

    def fit(self, df: pd.DataFrame):
        rows = team_rows(df)
        self.model = RidgeReg(self.alpha).fit(rows[self.features].to_numpy(float), rows.points.to_numpy(float))
        return self

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        rows = team_rows(df)
        pred = self.model.predict(rows[self.features].to_numpy(float))
        g = _game_level(rows, pred, df)
        return g[["pred_home", "pred_away", "pred_margin", "pred_total"]]

    def to_dict(self) -> dict:
        return {"features": self.features, "alpha": self.alpha, "coef": self.model.coefficients(self.features)}


class ServedPointsModel:
    """The shipped points model rebuilt from ml_models/points_model.json."""

    def __init__(self, path):
        import json
        with open(path) as f:
            d = json.load(f)
        self.features = list(d["features"])
        self.w = np.array([d["coef"][c] for c in self.features], dtype=float)
        self.b = float(d["coef"]["intercept"])

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        rows = team_rows(df)
        pred = rows[self.features].to_numpy(float) @ self.w + self.b
        g = _game_level(rows, pred, df)
        return g[["pred_home", "pred_away", "pred_margin", "pred_total"]]
