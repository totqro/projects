from datetime import datetime

import pandas as pd

from src.readiness import ET, game_readiness, report_due_et


def _g(day, time="13:00", home="CHI", away="MIN"):
    return pd.Series({"gameday": day, "gametime": time, "season": 2026, "week": 3,
                      "home_team": home, "away_team": away})


def test_report_deadlines():
    assert report_due_et(_g("2026-09-24", "20:15")) == datetime(2026, 9, 23, 16, tzinfo=ET)   # Thu -> Wed
    assert report_due_et(_g("2026-09-27")) == datetime(2026, 9, 25, 16, tzinfo=ET)            # Sun -> Fri
    assert report_due_et(_g("2026-09-28", "20:15")) == datetime(2026, 9, 26, 16, tzinfo=ET)   # Mon -> Sat


def test_readiness_rules():
    sat = datetime(2026, 9, 26, 18, tzinfo=ET)
    final = {(2026, 3, "CHI"): {"a": ("Out", "DNP")}, (2026, 3, "MIN"): {"b": ("NotListed", "Full")}}
    midweek = {(2026, 3, "CHI"): {"a": ("NotListed", "DNP")}, (2026, 3, "MIN"): {"b": ("NotListed", "Full")}}
    assert game_readiness(_g("2026-09-27"), final, sat) == (True, "ready")
    assert not game_readiness(_g("2026-09-27"), midweek, sat)[0]
    assert not game_readiness(_g("2026-09-27"), {(2026, 3, "CHI"): {"a": ("Out", "DNP")}}, sat)[0]
    assert not game_readiness(_g("2026-09-27"), final, datetime(2026, 9, 24, 12, tzinfo=ET))[0]  # too early
    assert game_readiness(_g("2026-09-27"), final, datetime(2026, 9, 27, 13, tzinfo=ET))[1] == "kicked off"
