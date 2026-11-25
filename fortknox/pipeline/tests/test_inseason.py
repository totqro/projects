"""Offline checks for the in-season xG recalibration (src/models/nhl_xg.py). Run: .venv/bin/python tests/test_inseason.py

Each shot's xG is scaled by its strength group's goals and xG on earlier dates of the season. These check
that a shot never sees its own date, that a season starts unscaled, that live scoring from a saved table
matches scoring the whole season, and that it moves a season that runs cold toward its goals.
"""
import json, sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.models.nhl_xg import INSEASON_K, inseason_adjust, inseason_table  # noqa: E402


def season(n_days=60, per_day=200, rate=0.08, seed=0):
    """A fake season: the model says 0.06 on every shot, goals go in at `rate`."""
    rng = np.random.default_rng(seed)
    days = [f"2026-10-{d:02d}" if d < 32 else f"2026-11-{d - 31:02d}" for d in range(1, n_days + 1)]
    dates = np.repeat(days, per_day)
    group = rng.choice(["5v5", "pp", "other"], size=len(dates), p=[0.7, 0.18, 0.12])
    goal = (rng.random(len(dates)) < rate).astype(float)
    return dates, group, goal, np.full(len(dates), 0.06)


def test_first_date_unscaled_and_no_same_day_peek():
    dates, group, goal, xg = season()
    t = inseason_table(dates, goal, xg, group)
    p = inseason_adjust(xg, dates, group, t)
    first = dates == dates[0]
    assert np.allclose(p[first], xg[first]), "the first date has nothing before it"
    # Changing a date's own goals must not change that date's xG.
    day = dates == "2026-10-20"
    goal2 = goal.copy(); goal2[day] = 1.0
    p2 = inseason_adjust(xg, dates, group, inseason_table(dates, goal2, xg, group))
    assert np.allclose(p[day], p2[day]) and not np.allclose(p[~day & (dates > "2026-10-20")],
                                                              p2[~day & (dates > "2026-10-20")])


def test_cold_season_moves_toward_goals():
    dates, group, goal, xg = season(rate=0.08)       # goals 33% above the model
    p = inseason_adjust(xg, dates, group, inseason_table(dates, goal, xg, group))
    assert xg.sum() / goal.sum() < p.sum() / goal.sum() < 1.0
    early, late = dates < "2026-10-15", dates >= "2026-11-15"
    gap = lambda m: abs(p[m].sum() / goal[m].sum() - 1)
    assert gap(late) < gap(early) - 0.1, "the more of the season it has seen, the closer it gets"


def test_live_from_saved_table_matches_whole_season():
    dates, group, goal, xg = season()
    t = inseason_table(dates, goal, xg, group)
    whole = inseason_adjust(xg, dates, group, t)
    last = dates == dates[-1]
    # nhl_live.py: tonight's games scored from the published table of the finished ones.
    saved = json.loads(json.dumps(inseason_table(dates[~last], goal[~last], xg[~last], group[~last])))
    live = inseason_adjust(xg[last], dates[last], group[last], saved)
    assert np.allclose(live, whole[last], atol=1e-6)


def test_factor_formula():
    dates = np.array(["2026-10-01", "2026-10-02"])
    group, xg, goal = np.array(["5v5", "5v5"]), np.array([0.1, 0.1]), np.array([1.0, 0.0])
    p = inseason_adjust(xg, dates, group, inseason_table(dates, goal, xg, group))
    r = (1 + INSEASON_K["5v5"]) / (0.1 + INSEASON_K["5v5"])
    assert np.isclose(p[1], 0.1 * r / (1 - 0.1 + 0.1 * r))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
