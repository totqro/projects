"""
nflverse loaders with a local on-disk cache and the game-type filter.
=====================================================================
Every dataset the model touches comes through here, for three reasons:

1. **One cache.** nflreadpy is pointed at ``nfllines/data/raw/`` (gitignored)
   in filesystem mode, so a full rebuild never re-downloads a season it
   already has, and the exact bytes a backtest ran on are on disk.
2. **No preseason, ever.** ``filter_game_types`` keeps only
   ``REG / WC / DIV / CON / SB`` (verified against the schedule file's
   ``game_type`` column — nflverse spells preseason ``PRE``). It is applied to
   schedules, play-by-play, snap counts and injuries alike, so no preseason
   play reaches an EPA total and no preseason snap reaches a snap share.
3. **Market columns stay out of the feature path.** The schedule file carries
   ``spread_line``, ``total_line``, ``home_moneyline``, ``away_moneyline``
   and a few derived columns. ``load_games`` returns them (the evaluation
   step needs them), but ``feature_frame`` strips them, and
   ``tests/test_market_ban.py`` fails the build if a feature column is ever
   derived from one. See MARKET_COLUMNS below.

Everything is returned as pandas — the modelling code is pandas/numpy, and
polars stays an implementation detail of the download.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import polars as pl

import nflreadpy as nfl
from nflreadpy import config as nfl_config

BASE_DIR = Path(__file__).resolve().parents[2]
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"

# nflverse game_type codes. PRE (preseason) is deliberately absent.
PLAYOFF_TYPES = ("WC", "DIV", "CON", "SB")
GAME_TYPES = ("REG",) + PLAYOFF_TYPES

# Betting-market columns in the nflverse schedule file. Evaluation-only.
# Anything computed from these is banned as a model input (hard rule 1).
MARKET_COLUMNS = (
    "spread_line", "total_line", "home_moneyline", "away_moneyline",
    "home_spread_odds", "away_spread_odds", "under_odds", "over_odds",
)

# Seasons. nflverse labels a season by its starting calendar year.
WARM_START_SEASON = 2014          # only to seed priors for week 1 of 2015
TRAIN_SEASONS = tuple(range(2015, 2024))   # 2015-2023 inclusive
TEST_SEASONS = (2024, 2025)               # untouched until the model is frozen
ALL_SEASONS = (WARM_START_SEASON,) + TRAIN_SEASONS + TEST_SEASONS


def _configure_cache() -> None:
    """nflreadpy's own disk cache holds a file for one day. Completed seasons
    are kept for good in the per-season parquet cache (cached_seasons), and
    the in-progress season bypasses every cache (see fresh()). A 365-day
    setting used here until 2026-09-21 froze the 2026 season at the first
    download: a week-3 run would have seen no week-2 results."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    nfl_config.update_config(cache_mode="filesystem", cache_dir=RAW_DIR,
                             cache_duration=24 * 3600, verbose=False)


_configure_cache()


def current_season(today=None) -> int:
    """The season in progress (or about to start): Aug-Dec -> this year,
    Jan-Jul -> last year."""
    import datetime as _dt
    today = today or _dt.date.today()
    return today.year if today.month >= 8 else today.year - 1


class fresh:
    """Context manager: bypass nflreadpy's cache for the enclosed downloads."""

    def __enter__(self):
        self._mode = nfl_config.get_config().cache_mode
        nfl_config.update_config(cache_mode="off")
        return self

    def __exit__(self, *exc):
        nfl_config.update_config(cache_mode=self._mode)
        return False


def _to_pandas(df: pl.DataFrame) -> pd.DataFrame:
    return df.to_pandas()


def filter_game_types(df: pd.DataFrame, col: str = "game_type") -> pd.DataFrame:
    """Drop every row that is not a regular-season or playoff game.

    Fails loudly if the column is missing — silently keeping preseason rows
    is exactly the failure mode this exists to prevent."""
    if col not in df.columns:
        raise KeyError(f"cannot filter game types: column {col!r} not in frame")
    keep = df[col].isin(GAME_TYPES)
    return df.loc[keep].reset_index(drop=True)


def load_games(seasons=ALL_SEASONS) -> pd.DataFrame:
    """Schedule + results for the requested seasons, REG + playoffs only.

    Keeps the market columns because evaluate_test.py needs them; every
    feature builder must go through ``feature_frame`` instead."""
    seasons = list(seasons)
    if max(seasons) >= current_season():
        with fresh():          # scores, starters and kickoff times change daily
            df = _to_pandas(nfl.load_schedules(seasons=seasons))
    else:
        df = _to_pandas(nfl.load_schedules(seasons=seasons))
    df = filter_game_types(df)
    df["gameday"] = pd.to_datetime(df["gameday"])
    df = df.sort_values(["gameday", "gametime", "game_id"]).reset_index(drop=True)
    return df


def feature_frame(games: pd.DataFrame) -> pd.DataFrame:
    """The schedule with every market column removed — the only version of
    the schedule any feature code is allowed to see."""
    drop = [c for c in MARKET_COLUMNS if c in games.columns]
    return games.drop(columns=drop)


def load_pbp(seasons) -> pd.DataFrame:
    """Play-by-play, REG + playoffs only, restricted to the columns the
    efficiency features need (the full file is ~370 columns per play)."""
    cols = [
        "game_id", "season", "week", "season_type", "game_date", "posteam", "defteam",
        "home_team", "away_team", "play_type", "epa", "success", "cpoe",
        "pass", "rush", "sack", "interception", "fumble_lost", "qb_dropback",
        "passer_player_id", "passer_player_name", "yards_gained", "special_teams_play",
        "complete_pass", "air_yards", "play_id", "desc", "qb_kneel", "qb_spike",
        "penalty", "aborted_play", "fumble", "fumble_forced", "fumble_not_forced",
        "fumble_out_of_bounds", "fumble_recovery_1_team", "two_point_attempt",
        "field_goal_result", "extra_point_result", "receiver_player_id",
        "rusher_player_id", "sack_player_id", "half_sack_1_player_id",
        "half_sack_2_player_id", "qb_hit", "qb_hit_1_player_id", "qb_hit_2_player_id",
        "wpa", "punt_attempt", "field_goal_attempt", "kickoff_attempt",
    ]
    frames = []
    for s in seasons:
        df = nfl.load_pbp(seasons=[int(s)])
        have = [c for c in cols if c in df.columns]
        df = df.select(have)
        pdf = _to_pandas(df)
        pdf = pdf.rename(columns={"season_type": "_season_type"})
        # nflverse pbp uses season_type in {REG, POST, PRE}; map to game_type
        # by joining game_id -> schedule instead of trusting it, but drop PRE here.
        pdf = pdf[pdf["_season_type"].isin(["REG", "POST"])]
        frames.append(pdf)
    out = pd.concat(frames, ignore_index=True)
    return out


def load_injuries(seasons) -> pd.DataFrame:
    df = _to_pandas(nfl.load_injuries(seasons=list(seasons)))
    return filter_game_types(df)


def load_snap_counts(seasons) -> pd.DataFrame:
    df = _to_pandas(nfl.load_snap_counts(seasons=list(seasons)))
    return filter_game_types(df)


def load_depth_charts(seasons) -> pd.DataFrame:
    return _to_pandas(nfl.load_depth_charts(seasons=list(seasons)))


def load_rosters_weekly(seasons) -> pd.DataFrame:
    return _to_pandas(nfl.load_rosters_weekly(seasons=list(seasons)))


def load_contracts() -> pd.DataFrame:
    return _to_pandas(nfl.load_contracts())


def load_draft_picks() -> pd.DataFrame:
    return _to_pandas(nfl.load_draft_picks())


def load_players() -> pd.DataFrame:
    return _to_pandas(nfl.load_players())


def load_pfr_advstats(seasons, stat_type: str) -> pd.DataFrame:
    return _to_pandas(nfl.load_pfr_advstats(seasons=list(seasons), stat_type=stat_type,
                                            summary_level="week"))


# --------------------------------------------------------------------------- #
# Per-season processed cache: data/processed/<name>/<season>.parquet          #
# --------------------------------------------------------------------------- #
def cached_seasons(name: str, loader, seasons, refresh_current: bool = True) -> pd.DataFrame:
    """Load `seasons` of a table through a per-season parquet cache. A season
    that is not on disk is fetched with `loader([season])` and written. The
    current (in-progress) season is always refetched so a live run sees the
    latest week; completed seasons are read from disk."""
    out = []
    d = PROCESSED_DIR / name
    d.mkdir(parents=True, exist_ok=True)
    current = current_season()
    for s in seasons:
        f = d / f"{int(s)}.parquet"
        live = refresh_current and int(s) >= current
        if f.exists() and not live:
            out.append(pd.read_parquet(f))
            continue
        if live:
            with fresh():
                df = loader([int(s)])
        else:
            df = loader([int(s)])
        df.to_parquet(f, index=False)
        out.append(df)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()
