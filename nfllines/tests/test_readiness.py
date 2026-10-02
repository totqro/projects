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


def test_backup_window():
    from src.readiness import backup_allowed
    g = _g("2026-09-27")                                                          # Sunday 1pm, report due Fri 4pm
    assert not backup_allowed(g, datetime(2026, 9, 25, 15, tzinfo=ET))           # before the deadline: wait
    assert backup_allowed(g, datetime(2026, 9, 25, 17, tzinfo=ET))               # deadline passed, report missing
    assert backup_allowed(g, datetime(2026, 9, 27, 12, 59, tzinfo=ET))           # last chance before kickoff
    assert not backup_allowed(g, datetime(2026, 9, 27, 13, tzinfo=ET))           # kicked off: never


def test_log_keeps_one_row_per_quality(tmp_path):
    from src.models.prediction_log import final_logged, log_predictions
    path = tmp_path / "log.jsonl"
    row = {"game_id": "2026_04_PIT_CLE", "home_win_prob": 0.34}
    assert log_predictions([{**row, "quality": "backup"}], path=path) == 1
    assert log_predictions([{**row, "quality": "backup"}], path=path) == 0        # same day, same quality
    assert final_logged(path) == set()
    assert log_predictions([{**row, "quality": "final"}], path=path) == 1         # full data later the same day
    assert final_logged(path) == {"2026_04_PIT_CLE"}


def test_scorecard_prefers_full_data_rows():
    from scorecard import pick_prediction
    ts = pd.to_datetime(["2026-10-01T20:00Z", "2026-10-01T21:00Z", "2026-10-01T22:00Z", "2026-10-01T21:00Z"], utc=True)
    pre = pd.DataFrame({"game_id": ["A", "A", "A", "B"], "ts": ts,
                        "quality": ["final", "backup", "backup", "backup"], "home_win_prob": [.6, .5, .4, .7]})
    picked = pick_prediction(pre)
    assert picked.loc["A", "home_win_prob"] == .6                                 # full-data row beats later backups
    assert picked.loc["B", "home_win_prob"] == .7                                 # backup used when it is all there is
