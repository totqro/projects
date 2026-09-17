"""
Serving: today's slate scored with the shipped, gated models.
=============================================================
Replays every completed game dated before today through the same
StateReplayer that builds the training rows, then snapshots features for
today's scheduled games. Training and serving share one feature function, so
there is no second implementation to drift.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from src.data.historical_dataset import (
    PLAYED_STATES, WIN_FEATURE_COLUMNS, TOTALS_FEATURE_COLUMNS,
    build_rows, load_history, seasons_through_current,
)
from src.models import totals_model, win_model

ET = ZoneInfo("America/New_York")


def today_et() -> str:
    return datetime.now(ET).strftime("%Y-%m-%d")


def score_slate(date: str = None, verbose: bool = True) -> dict:
    """Return {date, win_artifact, totals_artifact, games: [...]} for `date`
    (default: today, US/Eastern). Each game carries its features, calibrated
    home win probability, expected total and starter profiles."""
    date = date or today_et()
    season = int(date[:4])
    seasons = [s for s in seasons_through_current() if s <= season]
    if season not in seasons:
        seasons.append(season)

    win_art = win_model.load()
    totals_art = totals_model.load()

    schedules, index = load_history(seasons, verbose=verbose)
    _, replayer = build_rows(schedules, index, before_date=date)

    slate = [g for g in schedules.get(season, [])
             if g["date"] == date and g["state"] not in PLAYED_STATES
             and "Postponed" not in g["state"] and "Cancelled" not in g["state"]]
    slate.sort(key=lambda g: (g["game_datetime"], g["game_id"]))

    games = []
    for g in slate:
        f = replayer.features(g)
        missing = [c for c in WIN_FEATURE_COLUMNS + TOTALS_FEATURE_COLUMNS if c not in f]
        if missing:
            raise ValueError(f"serving features drifted from training columns: {missing}")
        games.append({
            **g,
            "features": f,
            "home_win_prob": win_model.predict(win_art, f),
            "expected_total": totals_model.predict(totals_art, f),
        })
    return {"date": date, "win_artifact": win_art, "totals_artifact": totals_art, "games": games}
