"""
The point-in-time feature engine: ONE code path for history and for serving.

Walks the schedule one (season, week) at a time. For every game in the week
it emits features from state that contains only earlier weeks; then, and
only then, it folds the week's results into the state. A live prediction is
the same walk over every completed week followed by ``features_for`` on the
upcoming game — so history and serving cannot drift apart, and
``tests/test_recompute.py`` checks that a from-scratch walk truncated
before a random game reproduces its stored row exactly.

Weekly granularity is deliberate: Thursday results are not used for
Sunday's features. That costs a sliver of information and buys a simple,
auditable rule ("week N features see weeks < N") that also matches how the
injury report cycle works.

Stages plug in as trackers; each is optional so the gate can compare
stage-by-stage on identical rows.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.features.elo import EloEngine, order_games
from src.features.qb import QBTracker


# The early-week prior features fade linearly to zero after this many games.
EARLY_GAMES = 6.0


def week_key(games: pd.DataFrame) -> pd.Series:
    return list(zip(games.season.astype(int), games.week.astype(int)))


class FeatureEngine:
    def __init__(self, elo_params: dict | None = None, qb_params: dict | None = None,
                 qb_elo_scale: float = 0.0, players: pd.DataFrame | None = None,
                 efficiency=None, injuries=None, week1_prior=None):
        elo_params = dict(elo_params or {})
        self.qb = QBTracker(players=players, **(qb_params or {}))
        self.qb_elo_scale = qb_elo_scale
        # Week-1 prior. In "feature mode" (coef=None, the shipped setting) the
        # Elo keeps flat reversion and the prior's inputs are emitted as
        # early-week features (see Stage 2 in README). With coefficients it
        # becomes the Elo season-start hook instead.
        self.week1_prior = week1_prior
        if week1_prior is not None:
            elo_params["season_start"] = week1_prior
        self.elo = EloEngine(qb_adjust=self._qb_adjust if qb_elo_scale else None, **elo_params)
        self.efficiency = efficiency        # optional EfficiencyTracker
        self.injuries = injuries            # optional InjuryTracker

    # -- hooks --------------------------------------------------------------- #
    def _qb_adjust(self, g: pd.Series) -> tuple[float, float]:
        season = int(g["season"])
        h = self.qb.rating(g.get("home_qb_id"), season)["qb_epa"]
        a = self.qb.rating(g.get("away_qb_id"), season)["qb_epa"]
        return self.qb_elo_scale * h, self.qb_elo_scale * a

    # -- features ------------------------------------------------------------ #
    def features_for(self, g: pd.Series) -> dict:
        season = int(g["season"])
        f = {"game_id": g["game_id"], "season": season, "week": int(g["week"]),
             "game_type": g["game_type"], "home_team": g["home_team"], "away_team": g["away_team"]}
        f.update(self.elo.pregame(g))
        hq = self.qb.rating(g.get("home_qb_id"), season)
        aq = self.qb.rating(g.get("away_qb_id"), season)
        f.update({"home_qb_epa": hq["qb_epa"], "away_qb_epa": aq["qb_epa"],
                  "home_qb_cpoe": hq["qb_cpoe"], "away_qb_cpoe": aq["qb_cpoe"],
                  "home_qb_n": hq["qb_n"], "away_qb_n": aq["qb_n"],
                  "qb_epa_diff": hq["qb_epa"] - aq["qb_epa"],
                  "qb_cpoe_diff": hq["qb_cpoe"] - aq["qb_cpoe"]})
        # situational (schedule-only, no state)
        neutral = 1.0 if g.get("location") == "Neutral" else 0.0
        f.update({
            "neutral": neutral,
            "home_rest": float(g["home_rest"]), "away_rest": float(g["away_rest"]),
            "rest_diff": float(g["home_rest"]) - float(g["away_rest"]),
            "home_off_bye": 1.0 if g["home_rest"] >= 13 else 0.0,
            "away_off_bye": 1.0 if g["away_rest"] >= 13 else 0.0,
            "home_short_week": 1.0 if g["home_rest"] <= 5 else 0.0,
            "away_short_week": 1.0 if g["away_rest"] <= 5 else 0.0,
            "div_game": float(g["div_game"]),
            "playoff": 0.0 if g["game_type"] == "REG" else 1.0,
            "dome": 1.0 if g.get("roof") in ("dome", "closed") else 0.0,
            "wind": float(g["wind"]) if pd.notna(g.get("wind")) and g.get("roof") == "outdoors" else 0.0,
            "temp": float(g["temp"]) if pd.notna(g.get("temp")) and g.get("roof") == "outdoors" else 70.0,
            # home-field advantage has declined over time; a linear trend term
            # lets the logistic fit a time-varying HFA (season index from 2015).
            "season_idx": float(season - 2015),
        })
        # games played this season (before this game), and the week-1 prior inputs
        gp_h = float(self.elo.games_played.get(g["home_team"], 0))
        gp_a = float(self.elo.games_played.get(g["away_team"], 0))
        f["home_games_played"], f["away_games_played"] = gp_h, gp_a
        if self.week1_prior is not None:
            ph = self.week1_prior.values.get((g["home_team"], season))
            pa = self.week1_prior.values.get((g["away_team"], season))
            early_h = max(0.0, 1.0 - gp_h / EARLY_GAMES)
            early_a = max(0.0, 1.0 - gp_a / EARLY_GAMES)
            f["home_last_team_pts"] = ph["last_team_pts"] if ph else 0.0
            f["away_last_team_pts"] = pa["last_team_pts"] if pa else 0.0
            f["home_snap_return"] = ph["snap_return"] if ph else 0.75
            f["away_snap_return"] = pa["snap_return"] if pa else 0.75
            f["home_coach_change"] = ph["coach_change"] if ph else 0.0
            f["away_coach_change"] = pa["coach_change"] if pa else 0.0
            f["home_last_epa_margin"] = ph["last_epa_margin"] if ph else 0.0
            f["away_last_epa_margin"] = pa["last_epa_margin"] if pa else 0.0
            # early-decayed differences: the logistic's chance to add back
            # whatever Elo's flat reversion threw away in the first weeks
            f["prior_last_team_pts_early_diff"] = f["home_last_team_pts"] * early_h - f["away_last_team_pts"] * early_a
            f["prior_snap_return_early_diff"] = (f["home_snap_return"] - 0.62) * early_h - (f["away_snap_return"] - 0.62) * early_a
            f["prior_coach_change_early_diff"] = f["home_coach_change"] * early_h - f["away_coach_change"] * early_a
            f["prior_last_epa_early_diff"] = f["home_last_epa_margin"] * early_h - f["away_last_epa_margin"] * early_a
        if self.efficiency is not None:
            f.update(self.efficiency.features(g))
        if self.injuries is not None:
            f.update(self.injuries.features(g))
        return f

    def end_week(self, wk_games: pd.DataFrame, wk_team_games: pd.DataFrame,
                 wk_qb_games: pd.DataFrame, wk_context: dict | None = None) -> None:
        # Elo first (uses QB ratings as of BEFORE this week's QB updates).
        for _, g in wk_games.iterrows():
            if pd.notna(g["home_score"]) and pd.notna(g["away_score"]):
                self.elo.update(g)
        self.qb.update_week(wk_qb_games)
        if self.efficiency is not None:
            self.efficiency.update_week(wk_games, wk_team_games)
        if self.injuries is not None:
            self.injuries.update_week(wk_games, wk_team_games, wk_context or {})

    # -- whole schedule -------------------------------------------------------- #
    def run(self, games: pd.DataFrame, team_games: pd.DataFrame, qb_games: pd.DataFrame,
            context: dict | None = None, stop_before: tuple | None = None,
            emit: bool = True) -> pd.DataFrame:
        """Walk every (season, week) in order. `stop_before=(season, week)`
        stops the walk with the state as it stood before that week (the
        serving / recomputation entry point). Returns the emitted rows."""
        games = order_games(games)
        rows = []
        tg_groups = {k: v for k, v in team_games.groupby(["season", "week"])}
        qb_groups = {k: v for k, v in qb_games.groupby(["season", "week"])}
        empty_tg = team_games.iloc[0:0]
        empty_qb = qb_games.iloc[0:0]
        for (season, week), wk in games.groupby(["season", "week"], sort=True):
            season, week = int(season), int(week)
            if stop_before is not None and (season, week) >= stop_before:
                break
            if self.efficiency is not None:
                self.efficiency.start_week(season, week)
            if self.injuries is not None:
                self.injuries.start_week(season, week, (context or {}))
            if emit:
                for _, g in wk.iterrows():
                    rows.append(self.features_for(g))
            played = wk[wk.home_score.notna()]
            self.end_week(played, tg_groups.get((season, week), empty_tg),
                          qb_groups.get((season, week), empty_qb), context)
        return pd.DataFrame(rows)
