"""
Stage 2 — the week-1 prior. Replaces Elo's flat 1/3 reversion with a fitted
season-start rating for the TEAM component (the QB-less part of the
QB-adjusted Elo; the starter's own value is added by the engine every week):

    pred_team_pts = a * last_team_pts + b * last_epa_margin + c * qb_change
                    + d * snap_return + e * coach_change + intercept

fit on team-seasons 2015-2023, LOSO by season. The target is the part of the
team's regular-season mean margin the engine does NOT already credit to the
QB: margin - (scale / elo_per_point) * mean pregame starter rating over the
season. The intercept and the shrinkage of `a` below 1 are the learned
regression toward the league mean.

Inputs, all available before the team's first game of the season:
    last_team_pts    (last season's final team-component Elo - 1500) / elo_per_point
    last_epa_margin  last season's raw EPA/play, offence minus defence
    qb_change        rating(first-game starter) - rating(last season's main QB),
                     both as the QB tracker rates them at season start
    snap_return      share of last season's non-QB offence+defence snaps taken by
                     players on this season's week-1 active roster
    coach_change     1 if the first game's head coach differs from last
                     season's

`elo_per_point` is measured (margin regressed on elo_diff over the training
games), not the 25-per-point folk constant, so the prior lands on the scale
this Elo actually runs on. The engine sets T = 1500 + elo_per_point * pred.

A first, wrong version predicted TOTAL strength and let the engine add the
starter back: every component lost to flat reversion because the QB was
being shrunk twice. Kept here as a warning.

Components are switched on one at a time in experiments/stage2_week1_prior.py
and each must improve LOSO log loss on weeks 1-4.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.features.elo import INITIAL_ELO, ELO_PER_POINT

Q_BAR = 0.03
COMPONENTS = ["last_team_pts", "last_epa_margin", "qb_change", "snap_return", "coach_change"]


def build_team_season_inputs(games: pd.DataFrame, team_games: pd.DataFrame, qb_games: pd.DataFrame,
                             snaps: pd.DataFrame, rosters: pd.DataFrame, players: pd.DataFrame) -> pd.DataFrame:
    """One row per (team, season) for season >= first season + 1, holding the
    LAST-season quantities and this season's week-1 roster continuity. No
    ratings here (those come from the live trackers at season start)."""
    reg = team_games[team_games.game_type == "REG"]
    ts = reg.groupby(["team", "season"]).agg(
        margin=("points", "mean"), pa=("points_allowed", "mean"),
        epa=("epa_sum", "sum"), plays=("plays", "sum"),
        depa=("def_epa_sum", "sum"), dplays=("def_plays", "sum"),
    ).reset_index()
    ts["margin"] = ts["margin"] - ts["pa"]
    ts["epa_margin"] = ts.epa / ts.plays - ts.depa / ts.dplays

    # main QB and coach last season
    qreg = qb_games[qb_games.game_type == "REG"].groupby(["team", "season", "qb_id"]).dropbacks.sum().reset_index()
    main_qb = qreg.sort_values("dropbacks", ascending=False).drop_duplicates(["team", "season"])[["team", "season", "qb_id"]]
    coaches = pd.concat([
        games[["season", "week", "game_type", "home_team", "home_coach"]].rename(columns={"home_team": "team", "home_coach": "coach"}),
        games[["season", "week", "game_type", "away_team", "away_coach"]].rename(columns={"away_team": "team", "away_coach": "coach"}),
    ])
    main_coach = coaches[coaches.game_type == "REG"].groupby(["team", "season"]).coach.agg(
        lambda s: s.value_counts().index[0]).reset_index()

    # returning snap share
    pfr2gsis = players.dropna(subset=["pfr_id"]).drop_duplicates("pfr_id").set_index("pfr_id").gsis_id
    sn = snaps[snaps.game_type == "REG"].copy()
    sn["gsis_id"] = sn.pfr_player_id.map(pfr2gsis)
    sn["team"] = sn.team.replace({"STL": "LA", "SD": "LAC", "OAK": "LV"})
    sn = sn[sn.position != "QB"]
    sn["snaps"] = sn.offense_snaps.fillna(0) + sn.defense_snaps.fillna(0)
    ps = sn.dropna(subset=["gsis_id"]).groupby(["team", "season", "gsis_id"]).snaps.sum().reset_index()
    ros = rosters[(rosters.week == 1) & (rosters.game_type == "REG") & (rosters.status == "ACT")]
    ros = ros[["team", "season", "gsis_id"]].drop_duplicates()
    ros["team"] = ros.team.replace({"STL": "LA", "SD": "LAC", "OAK": "LV"})
    ros = ros.assign(next_season=ros.season, season=ros.season - 1)
    j = ps.merge(ros.assign(on_roster=1)[["team", "season", "gsis_id", "on_roster"]],
                 on=["team", "season", "gsis_id"], how="left")
    j["on_roster"] = j.on_roster.fillna(0)
    ret = j.groupby(["team", "season"]).apply(
        lambda d: (d.snaps * d.on_roster).sum() / d.snaps.sum() if d.snaps.sum() else np.nan,
        include_groups=False).rename("snap_return").reset_index()

    last = ts[["team", "season", "epa_margin", "margin"]].merge(main_qb, on=["team", "season"], how="left") \
        .merge(main_coach, on=["team", "season"], how="left").merge(ret, on=["team", "season"], how="left")
    last = last.rename(columns={"epa_margin": "last_epa_margin", "margin": "last_margin",
                                "qb_id": "old_qb_id", "coach": "old_coach"})
    last["season"] = last.season + 1          # keyed by the season these are the PRIOR for
    target = ts[["team", "season", "margin"]].rename(columns={"margin": "target_margin"})
    out = last.merge(target, on=["team", "season"], how="left")
    return out


class Week1Prior:
    """Holds the per-(team, season) inputs and the fitted coefficients, and
    serves as the EloEngine.season_start hook."""

    def __init__(self, inputs: pd.DataFrame, qb_tracker, qb_elo_scale: float,
                 components: list | None = None, coef: dict | None = None,
                 elo_per_point: float = ELO_PER_POINT):
        self.inputs = inputs.set_index(["team", "season"])
        self.qb = qb_tracker
        self.scale = qb_elo_scale
        self.elo_per_point = elo_per_point
        self.components = list(components or COMPONENTS)
        self.coef = coef
        self.rows = []      # feature rows recorded at every season start (for fitting)
        self.values = {}    # (team, season) -> recorded feature dict (served as features)

    def features(self, team: str, season: int, last_rating: float, g) -> dict | None:
        key = (team, season)
        if key not in self.inputs.index:
            return None
        inp = self.inputs.loc[key]
        is_home = g["home_team"] == team
        new_qb = g["home_qb_id"] if is_home else g["away_qb_id"]
        new_coach = g["home_coach"] if is_home else g["away_coach"]
        q_new = self.qb.rating(new_qb, season)["qb_epa"]
        q_old = self.qb.rating(inp.old_qb_id, season)["qb_epa"] if pd.notna(inp.old_qb_id) else q_new
        return {
            "team": team, "season": season,
            "last_team_pts": (last_rating - INITIAL_ELO) / self.elo_per_point,
            "last_epa_margin": float(inp.last_epa_margin) if pd.notna(inp.last_epa_margin) else 0.0,
            "qb_change": q_new - q_old,
            "snap_return": float(inp.snap_return) if pd.notna(inp.snap_return) else 0.75,
            "coach_change": 0.0 if (pd.isna(inp.old_coach) or new_coach == inp.old_coach) else 1.0,
            "q_new": q_new,
            "target_margin": float(inp.target_margin) if pd.notna(inp.target_margin) else np.nan,
        }

    def predict_margin(self, f: dict) -> float:
        return self.coef["intercept"] + sum(self.coef.get(c, 0.0) * f[c] for c in self.components)

    def __call__(self, team: str, season: int, last_rating: float, g) -> float:
        f = self.features(team, season, last_rating, g)
        if f is None:
            return last_rating + (INITIAL_ELO - last_rating) / 3.0
        self.rows.append(f)
        self.values[(team, season)] = f
        if self.coef is None:      # recording pass / feature mode: flat reversion
            return last_rating + (INITIAL_ELO - last_rating) / 3.0
        pred = self.predict_margin(f)
        return INITIAL_ELO + self.elo_per_point * pred


def fit_prior(rows: pd.DataFrame, components: list, alpha: float = 1.0,
              target: str = "target_team_pts") -> dict:
    """Ridge (light) on raw units so coefficients are interpretable."""
    from sklearn.linear_model import Ridge
    d = rows.dropna(subset=[target])
    X = d[components].to_numpy(dtype=float)
    y = d[target].to_numpy(dtype=float)
    m = Ridge(alpha=alpha).fit(X, y)
    coef = dict(zip(components, map(float, m.coef_)))
    coef["intercept"] = float(m.intercept_)
    return coef
