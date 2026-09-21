"""
Stage 4 — injury adjustment, by position group, no double counting.

For each team before each game, over the players on that week's roster who
were on the roster for at least one of the team's last WINDOW games:

    adj_p   = value_p * (p_miss_p - missed_share_p)
    value_p = quality_p * snap_share_p
    inj_G   = sum of adj_p over players in position group G

* p_miss_p     1 - P(plays | final report status, practice) (measured table
               in src/data/injury_context.py); 1.0 for IR/PUP/suspended
               roster status; 0.05 when healthy and unlisted.
* missed_share the share of the WINDOW games (on the roster) the player did
               NOT play. The rolling efficiency ratings already reflect those
               absences, so only the CHANGE in availability is an adjustment:
               a returning starter is a positive number, a starter who has
               been out for the whole window contributes ~0 (his loss has
               been folded into the team's results).
* quality      contract APY as % of cap, plus draft capital exp(-(pick-1)/50)
               scaled by `draft_weight` (LOSO-chosen); the universal signal
               every position has. Position-specific stats are a later,
               separately gated step.
* snap_share   the player's mean snap share over the last games he played
               (for any team), default 0.25 if never seen.

QBs are excluded (Stage 1 handles the starter swap); K/P/LS are ignored.
"""
from __future__ import annotations

from collections import defaultdict, deque

import numpy as np
import pandas as pd

from src.data.injury_context import GROUPS, OUT_ROSTER_STATUS, P_PLAY_HEALTHY, p_play

WINDOW = 8
DEFAULT_SNAP_SHARE = 0.25
SNAP_HISTORY = 12


class InjuryTracker:
    def __init__(self, context: dict, draft_weight: float = 0.03, window: int = WINDOW):
        self.ctx = context
        self.draft_weight = draft_weight
        self.window = window
        self.team_games: dict[str, deque] = defaultdict(lambda: deque(maxlen=window))  # (season, week, game_id)
        self.player_snaps: dict[str, deque] = defaultdict(lambda: deque(maxlen=SNAP_HISTORY))
        self._season, self._week = None, None

    def start_week(self, season: int, week: int, context: dict) -> None:
        self._season, self._week = season, week

    def _quality(self, gsis: str, season: int) -> float:
        apy, dv = self.ctx["quality"](gsis, season)
        return apy + self.draft_weight * dv

    def team_adjustments(self, team: str, season: int, week: int) -> dict:
        roster = self.ctx["rosters"].get((season, week, team), {})
        report = self.ctx["injuries"].get((season, week, team), {})
        window = list(self.team_games[team])
        out = {g: 0.0 for g in GROUPS}
        out["n_listed"] = 0.0
        out["exp_starters_out_OL"] = 0.0
        if not window:
            return out
        # roster membership and played sets for the window games
        win_rosters = [self.ctx["rosters"].get((s, w, team), {}) for s, w, _ in window]
        win_played = [self.ctx["snaps"].get((gid, team), {}) for _, _, gid in window]
        # sorted: float sums must not depend on set order (hash seed varies per process)
        for p in sorted(set(roster) | set(report)):
            grp = self.ctx["positions"].get(p)
            if grp is None:
                continue
            on = [i for i, r in enumerate(win_rosters) if p in r]
            if not on:
                continue                      # new arrival: no baseline, Stage 2 territory
            played = [i for i in on if win_played[i].get(p, 0.0) > 0.0]
            missed_share = 1.0 - len(played) / len(on)
            status = roster.get(p)
            if p in report:
                st, pr = report[p]
                pm = 1.0 - p_play(st, pr)
                out["n_listed"] += 1.0
            elif status in OUT_ROSTER_STATUS or status is None:
                pm = 1.0
            else:
                pm = 1.0 - P_PLAY_HEALTHY
            hist = self.player_snaps.get(p)
            share = float(np.mean(hist)) if hist else DEFAULT_SNAP_SHARE
            value = self._quality(p, season) * share
            delta = pm - missed_share
            out[grp] += value * delta
            if grp == "OL" and share >= 0.5:
                out["exp_starters_out_OL"] += delta
        return out

    def features(self, g) -> dict:
        season, week = int(g["season"]), int(g["week"])
        h = self.team_adjustments(g["home_team"], season, week)
        a = self.team_adjustments(g["away_team"], season, week)
        f = {}
        for k, v in h.items():
            f[f"home_inj_{k}"] = v
        for k, v in a.items():
            f[f"away_inj_{k}"] = v
        for grp in GROUPS:
            f[f"inj_{grp}_diff"] = h[grp] - a[grp]
        f["inj_total_diff"] = sum(h[grp] for grp in GROUPS) - sum(a[grp] for grp in GROUPS)
        f["inj_OL_starters_diff"] = h["exp_starters_out_OL"] - a["exp_starters_out_OL"]
        return f

    def update_week(self, wk_games: pd.DataFrame, wk_team_games: pd.DataFrame, context: dict) -> None:
        for r in wk_team_games[["season", "week", "game_id", "team"]].itertuples(index=False):
            self.team_games[r.team].append((int(r.season), int(r.week), r.game_id))
            for p, pct in self.ctx["snaps"].get((r.game_id, r.team), {}).items():
                if pct > 0:
                    self.player_snaps[p].append(pct)
