"""
Elo with a margin-of-victory multiplier, an explicit home-field term and
season-boundary regression to the mean (FiveThirtyEight NFL style).

    diff      = elo_home - elo_away + HFA * is_home_venue
    p_home    = 1 / (1 + 10 ** (-diff / 400))
    mov_mult  = ln(|margin| + 1) * 2.2 / (winner_diff * 0.001 + 2.2)
    shift     = K * mov_mult * (actual_home - p_home)

Ratings are updated strictly in schedule order, and every game's stored
values are the ratings BEFORE that game. Teams play at most once per week,
so walking game-by-game and walking week-by-week give identical pregame
ratings; the feature engine relies on that.

Two hooks let later stages plug in without a second Elo implementation:

* ``season_start`` — how a team's rating is reset at its first game of a new
  season. Default: flat reversion of ``reversion`` toward 1500 (Stage 0).
  Stage 2 replaces it with the fitted week-1 prior.
* ``qb_adjust`` — a per-game (home_adj, away_adj) in Elo points added to the
  team ratings both for the expectation and for the update (so a loss with
  a backup QB doesn't get charged to the team rating). Stage 1.
"""
from __future__ import annotations

import math
from typing import Callable

import numpy as np
import pandas as pd

INITIAL_ELO = 1500.0
DEFAULT_K = 20.0
DEFAULT_HFA = 48.0
DEFAULT_REVERSION = 1.0 / 3.0
# 538's convention; the exact points-per-Elo ratio is refit downstream.
ELO_PER_POINT = 25.0


def elo_prob(diff: float) -> float:
    return 1.0 / (1.0 + 10.0 ** (-diff / 400.0))


class EloEngine:
    def __init__(self, k: float = DEFAULT_K, hfa: float = DEFAULT_HFA,
                 reversion: float = DEFAULT_REVERSION, mov: bool = True,
                 season_start: Callable[[str, int, float], float] | None = None,
                 qb_adjust: Callable[[pd.Series], tuple[float, float]] | None = None,
                 k_early_mult: float = 1.0, k_early_games: int = 0):
        self.k = k
        # Optional early-season K boost: K * k_early_mult for each team's
        # first `k_early_games` games of a season (Stage 2 experiment).
        self.k_early_mult = k_early_mult
        self.k_early_games = k_early_games
        self.games_played: dict[str, int] = {}
        self.hfa = hfa
        self.reversion = reversion
        self.mov = mov
        self.season_start = season_start
        self.qb_adjust = qb_adjust
        self.ratings: dict[str, float] = {}
        self.last_season: dict[str, int] = {}
        # (team, season) -> rating after that season's last game, before reset
        self.final_by_season: dict[tuple, float] = {}

    # -- state ---------------------------------------------------------- #
    def _prepare(self, team: str, season: int, g=None) -> None:
        if team not in self.ratings:
            self.ratings[team] = INITIAL_ELO
            self.last_season[team] = season
            self.games_played[team] = 0
        elif self.last_season[team] != season:
            r = self.ratings[team]
            self.final_by_season[(team, self.last_season[team])] = r
            if self.season_start is not None:
                self.ratings[team] = self.season_start(team, season, r, g)
            else:
                self.ratings[team] = r + (INITIAL_ELO - r) * self.reversion
            self.last_season[team] = season
            self.games_played[team] = 0

    def rating(self, team: str, season: int, g=None) -> float:
        """Current pregame rating for `team` in `season`, applying the
        season-start reset if the team hasn't played yet this season. `g` is
        the game row, handed to the season_start hook (the week-1 prior needs
        the first game's starting QB and coach)."""
        self._prepare(team, season, g)
        return self.ratings[team]

    # -- per game --------------------------------------------------------- #
    def pregame(self, g: pd.Series) -> dict:
        season = int(g["season"])
        home, away = g["home_team"], g["away_team"]
        r_home, r_away = self.rating(home, season, g), self.rating(away, season, g)
        adj_home, adj_away = (0.0, 0.0) if self.qb_adjust is None else self.qb_adjust(g)
        venue = 0.0 if g.get("location", "Home") == "Neutral" else 1.0
        diff = (r_home + adj_home) - (r_away + adj_away) + self.hfa * venue
        return {
            "elo_home": r_home, "elo_away": r_away,
            "elo_qb_adj_home": adj_home, "elo_qb_adj_away": adj_away,
            "elo_diff": diff,                       # includes HFA and QB adj
            "elo_diff_raw": r_home - r_away,        # team ratings only
            "elo_prob": elo_prob(diff),
        }

    def update(self, g: pd.Series, pre: dict | None = None) -> None:
        if pre is None:
            pre = self.pregame(g)
        margin = float(g["home_score"]) - float(g["away_score"])
        actual = 1.0 if margin > 0 else (0.0 if margin < 0 else 0.5)
        p = pre["elo_prob"]
        mult = 1.0
        if self.mov:
            winner_diff = pre["elo_diff"] if margin > 0 else -pre["elo_diff"]
            if margin == 0:
                winner_diff = 0.0
            mult = math.log(abs(margin) + 1.0) * 2.2 / (winner_diff * 0.001 + 2.2)
        shift = self.k * mult * (actual - p)
        home, away = g["home_team"], g["away_team"]
        if self.k_early_games:
            gp_h, gp_a = self.games_played.get(home, 0), self.games_played.get(away, 0)
            mh = self.k_early_mult if gp_h < self.k_early_games else 1.0
            ma = self.k_early_mult if gp_a < self.k_early_games else 1.0
            self.ratings[home] += shift * mh
            self.ratings[away] -= shift * ma
        else:
            self.ratings[home] += shift
            self.ratings[away] -= shift
        self.games_played[home] = self.games_played.get(home, 0) + 1
        self.games_played[away] = self.games_played.get(away, 0) + 1

    # -- whole schedule ---------------------------------------------------- #
    def run(self, games: pd.DataFrame) -> pd.DataFrame:
        """Walk completed games in order; return one pregame row per game.
        Games without a result are scored (pregame) but never update."""
        out = []
        for _, g in games.iterrows():
            pre = self.pregame(g)
            pre["game_id"] = g["game_id"]
            out.append(pre)
            if pd.notna(g.get("home_score")) and pd.notna(g.get("away_score")):
                self.update(g, pre)
        return pd.DataFrame(out).set_index("game_id")

    def final_ratings(self) -> dict:
        return dict(self.ratings)


def order_games(games: pd.DataFrame) -> pd.DataFrame:
    return games.sort_values(["season", "week", "gameday", "gametime", "game_id"]).reset_index(drop=True)
