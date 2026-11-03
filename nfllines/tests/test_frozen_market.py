"""The Vegas line is frozen at kickoff: a later nflverse revision never
changes a game that has started."""
from datetime import datetime, timedelta, timezone

import pandas as pd

import scorecard
from scorecard import apply_frozen_market, freeze_market

NOW = datetime(2026, 11, 1, 18, 0, tzinfo=timezone.utc)


def _res(p_started=0.504, p_future=0.6):
    return pd.DataFrame({
        "kickoff": [NOW - timedelta(hours=1), NOW + timedelta(hours=3)],
        "p_market": [p_started, p_future],
        "spread_line": [1.5, -3.0],
        "total_line": [41.5, 44.0],
    }, index=["started", "future"])


def test_started_game_keeps_its_pre_kickoff_line(tmp_path, monkeypatch):
    monkeypatch.setattr(scorecard, "FROZEN_PATH", tmp_path / "f.json")
    frozen = {"started": {"home_prob": 0.496, "spread": -1.0, "total": 42.0}}
    out = apply_frozen_market(_res(), NOW, frozen)
    assert out.at["started", "p_market"] == 0.496          # KC stays the favourite
    assert out.at["started", "spread_line"] == -1.0
    assert out.at["future", "p_market"] == 0.6             # not started: live line


def test_missing_fields_fall_back_to_nflverse():
    frozen = {"started": {"home_prob": 0.496, "spread": None, "total": None}}
    out = apply_frozen_market(_res(), NOW, frozen)
    assert out.at["started", "p_market"] == 0.496
    assert out.at["started", "spread_line"] == 1.5


def test_freeze_only_updates_games_not_started(tmp_path, monkeypatch):
    monkeypatch.setattr(scorecard, "FROZEN_PATH", tmp_path / "f.json")
    (tmp_path / "f.json").write_text('{"started": {"home_prob": 0.496, "spread": null, "total": null}}')
    frozen = freeze_market(_res(), NOW)
    assert frozen["started"]["home_prob"] == 0.496          # untouched after kickoff
    assert frozen["future"]["home_prob"] == 0.6
    assert frozen["future"]["spread"] == -3.0
