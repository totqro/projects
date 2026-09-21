"""
Point-in-time QB ratings: shrunk, season-decayed EPA per dropback.

    rating(qb) = (n0 * prior + sum_s lambda^(age_s) * epa_sum_s)
                 / (n0 + sum_s lambda^(age_s) * dropbacks_s)

`age_s` is how many seasons ago season s was (0 for the current one), so a
QB's current season counts fully and each earlier season is discounted.
`n0` pseudo-dropbacks of the prior make thin samples sit near the prior
instead of near their own noise: measured year-to-year correlation of
starters' EPA/dropback is 0.39 on ~500 dropbacks, which is what n0 ~ 700
reproduces. The prior is replacement level for anyone without a draft
pedigree, and a rookie-QB level for drafted players in their first two
seasons (measured 2014-2023: rookies with >= 100 dropbacks averaged about
-0.07 EPA/dropback regardless of draft slot; backups about -0.12).

CPOE is tracked the same way but is NOT folded into the rating: regressing
next-season EPA/dropback on (EPA/dropback, CPOE) gave CPOE a coefficient of
zero once EPA was included. It's exposed separately so the Stage 3 model can
test it as its own feature.

State only ever moves forward through ``update_week``; ``rating`` reads it.
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd

REPLACEMENT_EPA = -0.12
ROOKIE_PRIOR_EPA = -0.07
DEFAULT_N0 = 700.0
DEFAULT_DECAY = 0.6


class QBTracker:
    def __init__(self, n0: float = DEFAULT_N0, decay: float = DEFAULT_DECAY,
                 players: pd.DataFrame | None = None,
                 replacement: float = REPLACEMENT_EPA, rookie_prior: float = ROOKIE_PRIOR_EPA):
        self.n0 = n0
        self.decay = decay
        self.replacement = replacement
        self.rookie_prior = rookie_prior
        # qb_id -> season -> [dropbacks, epa_sum, cpoe_n, cpoe_sum]
        self.hist: dict[str, dict[int, list]] = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, 0.0, 0.0]))
        self.draft: dict[str, tuple] = {}
        if players is not None:
            p = players[players.position == "QB"].dropna(subset=["gsis_id"])
            for r in p.itertuples(index=False):
                self.draft[r.gsis_id] = (r.draft_round, r.rookie_season)

    def prior(self, qb_id: str, season: int) -> float:
        rnd, rookie_season = self.draft.get(qb_id, (np.nan, np.nan))
        if pd.notna(rnd) and rnd <= 2 and pd.notna(rookie_season) and season - rookie_season <= 1:
            return self.rookie_prior
        return self.replacement

    def rating(self, qb_id, season: int) -> dict:
        """Shrunk EPA/dropback, shrunk CPOE and the effective dropback count
        behind them, as of the current state. Unknown / missing QB ids get
        the replacement prior with zero history."""
        if qb_id is None or (isinstance(qb_id, float) and np.isnan(qb_id)):
            return {"qb_epa": self.replacement, "qb_cpoe": 0.0, "qb_n": 0.0}
        prior = self.prior(qb_id, season)
        w_db, s_epa, w_cp, s_cp = 0.0, 0.0, 0.0, 0.0
        for s, (db, epa, cn, cs) in self.hist.get(qb_id, {}).items():
            w = self.decay ** max(0, season - s)
            w_db += w * db
            s_epa += w * epa
            w_cp += w * cn
            s_cp += w * cs
        qb_epa = (self.n0 * prior + s_epa) / (self.n0 + w_db)
        qb_cpoe = s_cp / (self.n0 + w_cp)       # prior CPOE = 0
        return {"qb_epa": qb_epa, "qb_cpoe": qb_cpoe, "qb_n": w_db}

    def update_week(self, qb_games: pd.DataFrame) -> None:
        for r in qb_games.itertuples(index=False):
            h = self.hist[r.qb_id][int(r.season)]
            h[0] += float(r.dropbacks)
            h[1] += float(r.epa_sum)
            h[2] += float(r.cpoe_n)
            h[3] += float(r.cpoe_sum)
