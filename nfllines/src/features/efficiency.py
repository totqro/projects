"""
Rolling, opponent-adjusted efficiency ratings (Stage 3 features).

For every team the tracker keeps the per-game observations already played
and, each week, derives a rating per stat:

    in_season(stat)  = mean over this season's games of
                       (own value in game g  -  opponent's centred rating for the
                        mirror stat AS OF game g)           # opponent adjustment
    rating(stat)     = (n * in_season + n0 * prior) / (n + n0)

`prior` is the team's rating carried in from last season, regressed toward
the league mean by `carry` (Stage 2 swaps in the fitted week-1 prior); `n0`
is how many games of prior the new season's evidence has to outweigh. Both
are LOSO-fitted, not assumed.

The opponent adjustment uses the opponent's rating *at the time the game was
played* (stored when the week closed), never a later value — that is what
keeps a historical row identical to what a live run would have produced.

Stats (per play unless noted); `def_*` is what the team ALLOWED:
    epa, pass_epa, rush_epa, success, explosive, sack_rate (per dropback),
    int_rate (per dropback), fumble_lost_rate (per play), st_epa (per game),
    points (per game), plays (per game), pass_share
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd

RATE_STATS = {
    # name: (numerator col, denominator col)
    "epa": ("epa_sum", "plays"),
    "pass_epa": ("pass_epa_sum", "pass_plays"),
    "rush_epa": ("rush_epa_sum", "rush_plays"),
    "success": ("success_sum", "plays"),
    "explosive": ("explosive_sum", "plays"),
    "sack_rate": ("sacks_taken", "dropbacks"),
    "int_rate": ("int_thrown", "dropbacks"),
    "fumble_lost_rate": ("fumbles_lost", "plays"),
}
PER_GAME_STATS = ["st_epa_net", "points", "plays"]
STAT_NAMES = list(RATE_STATS) + PER_GAME_STATS + ["pass_share"]
SIDES = ("off", "def")
DEFAULT_N0 = 5.0
DEFAULT_CARRY = 0.5


def _game_values(r) -> dict:
    """Per-game per-stat values for one team-game row (both sides)."""
    v = {}
    for name, (num, den) in RATE_STATS.items():
        v[("off", name)] = r[num] / r[den] if r[den] else 0.0
        v[("def", name)] = r[f"def_{num}"] / r[f"def_{den}"] if r[f"def_{den}"] else 0.0
    v[("off", "st_epa_net")] = r["st_epa_net"]
    v[("def", "st_epa_net")] = -r["st_epa_net"]
    v[("off", "points")] = r["points"]
    v[("def", "points")] = r["points_allowed"]
    v[("off", "plays")] = r["plays"]
    v[("def", "plays")] = r["def_plays"]
    v[("off", "pass_share")] = r["pass_plays"] / r["plays"] if r["plays"] else 0.5
    v[("def", "pass_share")] = r["def_pass_plays"] / r["def_plays"] if r["def_plays"] else 0.5
    return v


class EfficiencyTracker:
    def __init__(self, n0: float = DEFAULT_N0, carry: float = DEFAULT_CARRY,
                 prior_fn=None):
        self.n0 = n0
        self.carry = carry
        self.prior_fn = prior_fn          # optional callable(team, season, stat_key, last_rating, league_mean) -> prior
        self.season_games: dict[str, list] = defaultdict(list)   # team -> [adjusted value dicts] this season
        self.season_raw: dict[str, list] = defaultdict(list)     # team -> [raw value dicts] this season
        self.team_season: dict[str, int] = {}
        self.prior: dict[str, dict] = {}                          # team -> {stat_key: prior}
        self.last_final: dict[str, dict] = {}                     # team -> ratings at end of last season
        self.ratings: dict[str, dict] = {}                        # team -> current {stat_key: rating}
        self.league_mean: dict = {k: 0.0 for k in _all_keys()}
        self.history: dict[int, dict] = {}                        # season -> team -> final ratings

    # -- season handling ------------------------------------------------------- #
    def _ensure_season(self, team: str, season: int) -> None:
        """Only a team never seen before is initialised here (at the league
        mean); every other transition is done in start_week()."""
        if team in self.ratings:
            if self.team_season.get(team) != season:
                self._transition(team, season, self._league_mean_snapshot())
            return
        lm = self._league_mean_snapshot()
        self.prior[team] = dict(lm)
        self.ratings[team] = dict(lm)
        self.season_games[team] = []
        self.season_raw[team] = []
        self.team_season[team] = season

    def _league_mean_snapshot(self) -> dict:
        if not self.ratings:
            return {k: 0.0 for k in _all_keys()}
        out = {}
        teams = sorted(self.ratings)      # fixed order -> bit-identical sums
        for key in _all_keys():
            vals = [self.ratings[t][key] for t in teams]
            out[key] = float(np.mean(vals))
        return out

    def start_week(self, season: int, week: int) -> None:
        """Season transitions happen HERE, for every known team in sorted
        order from ONE league-mean snapshot — never lazily on first query.
        (A lazy version made a team's prior depend on which other teams had
        already been queried that week: history and serving disagreed in the
        4th decimal. The recomputation test caught it.)"""
        if getattr(self, "_current_season", None) == season:
            return
        self._current_season = season
        for team in sorted(self.ratings):
            self._transition(team, season, self._league_mean_snapshot())

    def _transition(self, team: str, season: int, lm: dict) -> None:
        last = self.ratings.get(team)
        self.last_final[team] = dict(last)
        prior = {}
        for key in _all_keys():
            base = lm[key]
            if self.prior_fn is not None:
                prior[key] = self.prior_fn(team, season, key, last[key], base)
            else:
                prior[key] = base + self.carry * (last[key] - base)
        self.prior[team] = prior
        self.ratings[team] = dict(prior)
        self.season_games[team] = []
        self.season_raw[team] = []
        self.team_season[team] = season

    # -- read ----------------------------------------------------------------- #
    def rating(self, team: str, season: int) -> dict:
        self._ensure_season(team, season)
        return self.ratings[team]

    def n_games(self, team: str, season: int) -> int:
        self._ensure_season(team, season)
        return len(self.season_games[team])

    def features(self, g) -> dict:
        season = int(g["season"])
        h, a = self.rating(g["home_team"], season), self.rating(g["away_team"], season)
        lm = self.league_mean
        f = {}
        for side in SIDES:
            for name in STAT_NAMES:
                key = (side, name)
                f[f"home_{side}_{name}"] = h[key]
                f[f"away_{side}_{name}"] = a[key]
        # headline differences the win model actually uses
        f["epa_margin_diff"] = (h[("off", "epa")] - h[("def", "epa")]) - (a[("off", "epa")] - a[("def", "epa")])
        f["off_epa_diff"] = h[("off", "epa")] - a[("off", "epa")]
        f["def_epa_diff"] = h[("def", "epa")] - a[("def", "epa")]
        f["pass_epa_margin_diff"] = (h[("off", "pass_epa")] - h[("def", "pass_epa")]) - (a[("off", "pass_epa")] - a[("def", "pass_epa")])
        f["rush_epa_margin_diff"] = (h[("off", "rush_epa")] - h[("def", "rush_epa")]) - (a[("off", "rush_epa")] - a[("def", "rush_epa")])
        f["success_margin_diff"] = (h[("off", "success")] - h[("def", "success")]) - (a[("off", "success")] - a[("def", "success")])
        f["explosive_margin_diff"] = (h[("off", "explosive")] - h[("def", "explosive")]) - (a[("off", "explosive")] - a[("def", "explosive")])
        f["sack_margin_diff"] = (h[("def", "sack_rate")] - h[("off", "sack_rate")]) - (a[("def", "sack_rate")] - a[("off", "sack_rate")])
        f["turnover_margin_diff"] = ((h[("def", "int_rate")] + h[("def", "fumble_lost_rate")]) - (h[("off", "int_rate")] + h[("off", "fumble_lost_rate")])) \
            - ((a[("def", "int_rate")] + a[("def", "fumble_lost_rate")]) - (a[("off", "int_rate")] + a[("off", "fumble_lost_rate")]))
        f["st_epa_diff"] = h[("off", "st_epa_net")] - a[("off", "st_epa_net")]
        f["points_margin_diff"] = (h[("off", "points")] - h[("def", "points")]) - (a[("off", "points")] - a[("def", "points")])
        # "luck": points margin minus EPA-implied margin (per game), and
        # turnover luck (fumble recovery rate regresses to 50%)
        return f

    # -- update ------------------------------------------------------------------ #
    def update_week(self, wk_games: pd.DataFrame, wk_team_games: pd.DataFrame) -> None:
        if wk_team_games.empty:
            return
        season = int(wk_team_games.season.iloc[0])
        # Opponent ratings as of before this week, for every team playing.
        pre = {}
        for team in sorted(set(wk_team_games.team) | set(wk_team_games.opp)):
            pre[team] = dict(self.rating(team, season))
        lm = dict(self.league_mean)
        for r in wk_team_games.to_dict("records"):
            team, opp = r["team"], r["opp"]
            raw = _game_values(r)
            adj = {}
            for (side, name), val in raw.items():
                mirror = ("def", name) if side == "off" else ("off", name)
                adj[(side, name)] = val - (pre[opp][mirror] - lm[mirror])
            self.season_raw[team].append(raw)
            self.season_games[team].append(adj)
        # Recompute ratings for the teams that played.
        for team in sorted(set(wk_team_games.team)):
            n = len(self.season_games[team])
            prior = self.prior[team]
            new = {}
            for key in _all_keys():
                mean_adj = float(np.mean([gv[key] for gv in self.season_games[team]]))
                new[key] = (n * mean_adj + self.n0 * prior[key]) / (n + self.n0)
            self.ratings[team] = new
        self.league_mean = self._league_mean_snapshot()

    def season_summary(self, team: str) -> dict | None:
        """Raw (unadjusted) per-game means for the team's current season —
        the Stage 2 week-1 prior reads last season's from `last_final`."""
        if not self.season_raw.get(team):
            return None
        keys = _all_keys()
        return {k: float(np.mean([gv[k] for gv in self.season_raw[team]])) for k in keys}


def _all_keys():
    return [(side, name) for side in SIDES for name in STAT_NAMES]


class EWMATracker(EfficiencyTracker):
    """Exponentially weighted variant (the one that ships):

        rating = (n0 * league_mean + sum_i w_i * adj_i) / (n0 + sum_i w_i)
        w_i    = lam ** (games ago) * season_discount ** (seasons ago)

    Same opponent adjustment as the base class; no separate prior/carry —
    last season's games simply carry a discounted weight, so the season
    boundary is a soft one. LOSO (experiments/stage3b_ewma.py): lam 0.9,
    season_discount 0.8, n0 6 — a hair better than season-mean + carry, and
    one fewer moving part."""

    def __init__(self, lam: float = 0.9, season_discount: float = 0.8, n0: float = 6.0):
        super().__init__(n0=n0, carry=0.0)
        self.lam = lam
        self.season_discount = season_discount
        self.all_games: dict[str, list] = {}

    def _transition(self, team: str, season: int, lm: dict) -> None:
        self.team_season[team] = season
        self.season_games[team] = []
        self.season_raw[team] = []
        self._recompute(team, season, lm)

    def _ensure_season(self, team: str, season: int) -> None:
        if team not in self.ratings:
            self.ratings[team] = dict(self._league_mean_snapshot())
            self.all_games[team] = []
            self._transition(team, season, self._league_mean_snapshot())
        elif self.team_season.get(team) != season:
            self._transition(team, season, self._league_mean_snapshot())

    def _recompute(self, team: str, season: int, lm: dict | None = None) -> None:
        lm = lm if lm is not None else self._league_mean_snapshot()
        hist = self.all_games.get(team, [])
        new = {}
        for key in _all_keys():
            wsum, vsum = self.n0, self.n0 * lm[key]
            for i, (s, adj) in enumerate(reversed(hist)):
                w = (self.lam ** i) * (self.season_discount ** (season - s))
                wsum += w
                vsum += w * adj[key]
            new[key] = vsum / wsum
        self.ratings[team] = new

    def update_week(self, wk_games: pd.DataFrame, wk_team_games: pd.DataFrame) -> None:
        if wk_team_games.empty:
            return
        season = int(wk_team_games.season.iloc[0])
        pre = {t: dict(self.rating(t, season)) for t in sorted(set(wk_team_games.team) | set(wk_team_games.opp))}
        lm = dict(self.league_mean)
        for r in wk_team_games.sort_values(["game_id", "team"]).to_dict("records"):
            raw = _game_values(r)
            adj = {}
            for (side, name), val in raw.items():
                mirror = ("def", name) if side == "off" else ("off", name)
                adj[(side, name)] = val - (pre[r["opp"]][mirror] - lm[mirror])
            self.all_games[r["team"]].append((season, adj))
            self.season_games[r["team"]].append(adj)
            self.season_raw[r["team"]].append(raw)
        lm_now = self._league_mean_snapshot()
        for t in sorted(set(wk_team_games.team)):
            self._recompute(t, season, lm_now)
        self.league_mean = self._league_mean_snapshot()
