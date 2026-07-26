"""
MoneyPuck shot-level expected-goals (xG) data.
================================================
Source: MoneyPuck's public shots dataset, one zip per season
(https://moneypuck.com/moneypuck/playerData/shots/shots_{YEAR}.zip, ~20MB
zipped CSV). Every row is one shot, tagged with game_id, xGoal,
homeTeamCode/awayTeamCode, teamCode (the shooting team), isHomeTeam, score
state (home/awayTeamGoals at the time of the shot), and strength state
(home/awaySkatersOnIce).

This module aggregates shots to per-game, per-team totals:
- xgf / xga: raw expected goals for/against, all situations.
- xgf_adj / xga_adj: "adjusted" xG for/against, restricted to 5v5 shots with
  the score within one goal (the standard public "5v5 close" situational
  filter used across hockey analytics sites to strip out score-effect bias).
  The raw shots file has no pre-computed score/venue-adjusted xG column, so
  this is the honest stand-in rather than a fabricated multiplier table.
- hd_xgf / hd_xga: high-danger expected goals for/against — shots with
  xGoal >= HIGH_DANGER_XG_THRESHOLD (roughly the shot-quality top quartile;
  the raw file has no MoneyPuck shot-danger tier either, so this is a
  practical proxy).

Downloaded zips are cached under cache/ forever — a completed season's shot
log never changes.
"""

import csv
import io
import time
import zipfile
from datetime import datetime
from pathlib import Path

import requests

from .nhl_data import CACHE_DIR

# A season's shots zip is downloaded once and cached forever — EXCEPT for the
# season currently in progress, whose zip MoneyPuck keeps appending to. That
# season's cache is treated as stale after this many hours so serving picks
# up newly published games instead of freezing on whatever was cached first
# (which would otherwise make the in-season xG lag permanent, not just a
# lag). Mirrors historical_dataset.py's _CURRENT_SEASON_CACHE_HOURS pattern.
_CURRENT_SEASON_SHOTS_CACHE_HOURS = 12


def _current_season_start_year() -> int:
    # Duplicated from historical_dataset.current_season() rather than
    # imported: historical_dataset.py imports load_moneypuck_xg from this
    # module, so importing back would be circular.
    now = datetime.now()
    return now.year if now.month >= 7 else now.year - 1

MONEYPUCK_SHOTS_URL = "https://moneypuck.com/moneypuck/playerData/shots/shots_{year}.zip"

# MoneyPuck's server 302-redirects to a license page for bare requests
# without a browser-like User-Agent/Referer.
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; nhllines-research/1.0)",
    "Referer": "https://moneypuck.com/data.htm",
}

HIGH_DANGER_XG_THRESHOLD = 0.08  # ~top quartile of shot quality, see module docstring

# MoneyPuck team codes -> NHL API abbreviations. The 2022-2025 shots files
# already use NHL-API-style codes (NJD/TBL/LAK/SJS/UTA/...), but MoneyPuck's
# other endpoints (and older archives) use the dotted "N.J"/"T.B"/"L.A"/"S.J"
# style, so both are mapped explicitly. Any code NOT in this map raises
# immediately in _map_team() rather than being silently dropped.
MONEYPUCK_TO_NHL = {
    "ANA": "ANA", "ARI": "ARI", "PHX": "ARI",  # PHX: pre-2014 Phoenix, defensive
    "BOS": "BOS", "BUF": "BUF", "CAR": "CAR", "CBJ": "CBJ", "CGY": "CGY",
    "CHI": "CHI", "COL": "COL", "DAL": "DAL", "DET": "DET", "EDM": "EDM",
    "FLA": "FLA",
    "LAK": "LAK", "L.A": "LAK",
    "MIN": "MIN", "MTL": "MTL",
    "NJD": "NJD", "N.J": "NJD",
    "NSH": "NSH", "NYI": "NYI", "NYR": "NYR", "OTT": "OTT", "PHI": "PHI",
    "PIT": "PIT", "SEA": "SEA",
    "SJS": "SJS", "S.J": "SJS",
    "STL": "STL",
    "TBL": "TBL", "T.B": "TBL",
    "TOR": "TOR", "UTA": "UTA", "VAN": "VAN", "VGK": "VGK", "WPG": "WPG",
    "WSH": "WSH",
}


def _cache_csv_path(year: int) -> Path:
    return CACHE_DIR / f"moneypuck_shots_{year}.csv"


def download_season_shots(year: int) -> Path:
    """Download+cache one season's shots zip; return the path to the
    extracted CSV. Cached forever once present — a completed season's shot
    log doesn't change."""
    csv_path = _cache_csv_path(year)
    if csv_path.exists():
        if year != _current_season_start_year():
            return csv_path
        age_hours = (time.time() - csv_path.stat().st_mtime) / 3600
        if age_hours < _CURRENT_SEASON_SHOTS_CACHE_HOURS:
            return csv_path

    url = MONEYPUCK_SHOTS_URL.format(year=year)
    resp = requests.get(url, headers=_HEADERS, timeout=180)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = [n for n in zf.namelist() if n.endswith(".csv")]
        if not names:
            raise ValueError(f"No CSV found in MoneyPuck shots zip for {year}")
        tmp_path = csv_path.with_suffix(".csv.tmp")
        with zf.open(names[0]) as src, open(tmp_path, "wb") as dst:
            dst.write(src.read())
        tmp_path.replace(csv_path)
    return csv_path


def _map_team(code: str) -> str:
    mapped = MONEYPUCK_TO_NHL.get(code)
    if mapped is None:
        raise ValueError(
            f"Unrecognized MoneyPuck team code {code!r} — add it to "
            f"MONEYPUCK_TO_NHL in src/data/moneypuck_data.py. Refusing to "
            f"silently drop this team's shots."
        )
    return mapped


def _new_team_totals(is_home: bool) -> dict:
    return {
        "is_home": is_home,
        "xgf": 0.0, "xga": 0.0,
        "xgf_adj": 0.0, "xga_adj": 0.0,
        "hd_xgf": 0.0, "hd_xga": 0.0,
    }


def aggregate_season_game_team_xg(year: int) -> dict:
    """
    Parse one season's shots CSV and aggregate to per-game, per-team totals.

    Returns {nhl_game_id: {team_abbrev: {...}}}, always exactly two teams
    per game. nhl_game_id is reconstructed to match the NHL API's format
    (e.g. 2022020001) so it joins directly onto historical_dataset.py's game
    ids: season_year * 1_000_000 + MoneyPuck's within-season game_id (which
    is itself the NHL id's game-type + game-number suffix, e.g. "20001" for
    the type-02 game number 0001 — MoneyPuck's game_id integer already
    equals that suffix with leading zeros stripped).
    """
    csv_path = download_season_shots(year)
    games = {}  # nhl_game_id -> {team_abbrev: {...}}

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("isPlayoffGame") != "0":
                continue  # regular season only, matches historical_dataset.py

            nhl_game_id = year * 1_000_000 + int(row["game_id"])

            home_team = _map_team(row["homeTeamCode"])
            away_team = _map_team(row["awayTeamCode"])
            shooting_team = _map_team(row["teamCode"])
            is_home_shot = shooting_team == home_team
            defending_team = away_team if is_home_shot else home_team

            xg = float(row["xGoal"] or 0.0)
            is_close_5v5 = (
                row.get("homeSkatersOnIce") == "5"
                and row.get("awaySkatersOnIce") == "5"
                and abs(int(float(row.get("homeTeamGoals") or 0))
                        - int(float(row.get("awayTeamGoals") or 0))) <= 1
            )
            is_high_danger = xg >= HIGH_DANGER_XG_THRESHOLD

            g = games.setdefault(nhl_game_id, {})
            shooter = g.setdefault(shooting_team, _new_team_totals(is_home_shot))
            defender = g.setdefault(defending_team, _new_team_totals(not is_home_shot))

            shooter["xgf"] += xg
            defender["xga"] += xg
            if is_close_5v5:
                shooter["xgf_adj"] += xg
                defender["xga_adj"] += xg
            if is_high_danger:
                shooter["hd_xgf"] += xg
                defender["hd_xga"] += xg

    # Every game must resolve to exactly two teams, one home and one away —
    # fail loudly rather than silently dropping a mismatched game.
    for gid, teams in games.items():
        if len(teams) != 2:
            raise ValueError(
                f"MoneyPuck game {gid} (season {year}) aggregated to "
                f"{len(teams)} teams ({sorted(teams)}), expected 2 — "
                f"team-mapping or parsing bug."
            )
        n_home = sum(1 for t in teams.values() if t["is_home"])
        if n_home != 1:
            raise ValueError(
                f"MoneyPuck game {gid} (season {year}) has {n_home} teams "
                f"flagged home, expected exactly 1."
            )

    return games


_SEASON_CACHE = {}  # year -> aggregated dict, in-process memoization


def load_moneypuck_xg(seasons: list) -> dict:
    """
    Load and merge per-game team xG aggregates for every season in
    `seasons` (season strings like '20222023', matching
    historical_dataset.py's season format). Returns
    {nhl_game_id: {team_abbrev: {...}}}.
    """
    merged = {}
    for season in seasons:
        year = int(season[:4])
        if year not in _SEASON_CACHE:
            _SEASON_CACHE[year] = aggregate_season_game_team_xg(year)
        merged.update(_SEASON_CACHE[year])
    return merged
