"""
One row per team-game (offence-side box of EPA-based stats) from play-by-play,
plus one row per QB-game. These are the raw per-game observations every
rolling feature is built from. Nothing here is a feature yet — a row for game
G describes what happened IN game G, and the feature engine only ever reads
rows from earlier weeks.

Team codes are normalised to the current abbreviation (STL->LA, SD->LAC,
OAK->LV) so a franchise's rating survives relocation. nflverse play-by-play
already uses the current codes; the schedule file does not.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.data import nflverse as nv

TEAM_RENAME = {"STL": "LA", "SD": "LAC", "OAK": "LV"}

EXPLOSIVE_PASS_YDS = 20
EXPLOSIVE_RUSH_YDS = 10


def normalize_team(s: pd.Series) -> pd.Series:
    return s.replace(TEAM_RENAME)


def normalize_games(games: pd.DataFrame) -> pd.DataFrame:
    g = games.copy()
    for c in ("home_team", "away_team"):
        g[c] = normalize_team(g[c])
    return g


def _load_pbp(seasons) -> pd.DataFrame:
    return nv.cached_seasons("pbp", nv.load_pbp, seasons)


def build_team_games(games: pd.DataFrame, pbp: pd.DataFrame | None = None) -> pd.DataFrame:
    """Per (game_id, team) offensive stats + net special-teams EPA + points.

    Defensive stats are the opponent's offensive line in the same game, so
    each row also carries `def_*` columns copied from the opposing row."""
    games = normalize_games(games)
    if pbp is None:
        pbp = _load_pbp(sorted(games.season.unique()))
    pbp = pbp[pbp.game_id.isin(set(games.game_id))].copy()

    # Scrimmage plays only: pass or rush with EPA, no kneels/spikes.
    scrim = pbp[((pbp["pass"] == 1) | (pbp["rush"] == 1))
                & pbp.epa.notna() & (pbp.qb_kneel != 1) & (pbp.qb_spike != 1)
                & pbp.posteam.notna()].copy()
    scrim["is_pass"] = (scrim["pass"] == 1).astype(int)
    scrim["is_rush"] = (scrim["rush"] == 1).astype(int)
    scrim["pass_epa"] = scrim.epa * scrim.is_pass
    scrim["rush_epa"] = scrim.epa * scrim.is_rush
    scrim["explosive"] = (((scrim.is_pass == 1) & (scrim.yards_gained >= EXPLOSIVE_PASS_YDS))
                          | ((scrim.is_rush == 1) & (scrim.yards_gained >= EXPLOSIVE_RUSH_YDS))).astype(int)
    scrim["sack"] = scrim["sack"].fillna(0)
    scrim["interception"] = scrim["interception"].fillna(0)
    scrim["fumble_lost"] = scrim["fumble_lost"].fillna(0)
    scrim["fumble"] = scrim["fumble"].fillna(0)
    scrim["cpoe_n"] = scrim.cpoe.notna().astype(int)
    scrim["cpoe_sum"] = scrim.cpoe.fillna(0.0)
    scrim["dropback"] = scrim.qb_dropback.fillna(0)
    scrim["success"] = scrim.success.fillna(0)

    agg = scrim.groupby(["game_id", "posteam"]).agg(
        plays=("epa", "size"), epa_sum=("epa", "sum"),
        pass_plays=("is_pass", "sum"), pass_epa_sum=("pass_epa", "sum"),
        rush_plays=("is_rush", "sum"), rush_epa_sum=("rush_epa", "sum"),
        success_sum=("success", "sum"), explosive_sum=("explosive", "sum"),
        dropbacks=("dropback", "sum"), sacks_taken=("sack", "sum"),
        int_thrown=("interception", "sum"), fumbles_lost=("fumble_lost", "sum"),
        fumbles=("fumble", "sum"), cpoe_n=("cpoe_n", "sum"), cpoe_sum=("cpoe_sum", "sum"),
    ).reset_index().rename(columns={"posteam": "team"})

    # Net special-teams EPA per team-game (kick/punt/FG/XP plays).
    st = pbp[(pbp.special_teams_play == 1) & pbp.epa.notna()]
    st_for = st.groupby(["game_id", "posteam"]).epa.sum().rename("st_epa_for")
    st_against = st.groupby(["game_id", "defteam"]).epa.sum().rename("st_epa_against")
    st_for.index.names = ["game_id", "team"]
    st_against.index.names = ["game_id", "team"]

    agg = agg.merge(st_for.reset_index(), on=["game_id", "team"], how="left")
    agg = agg.merge(st_against.reset_index(), on=["game_id", "team"], how="left")
    agg["st_epa_net"] = agg.st_epa_for.fillna(0) - agg.st_epa_against.fillna(0)

    # Points, opponent, home flag from the schedule.
    home = games[["game_id", "season", "week", "game_type", "gameday", "home_team", "away_team",
                  "home_score", "away_score"]].copy()
    rows = pd.concat([
        home.assign(team=home.home_team, opp=home.away_team, is_home=1,
                    points=home.home_score, points_allowed=home.away_score),
        home.assign(team=home.away_team, opp=home.home_team, is_home=0,
                    points=home.away_score, points_allowed=home.home_score),
    ])[["game_id", "season", "week", "game_type", "gameday", "team", "opp", "is_home",
        "points", "points_allowed"]]
    tg = rows.merge(agg, on=["game_id", "team"], how="left")

    # Defensive side = the opponent's offensive line in this game.
    off_cols = ["plays", "epa_sum", "pass_plays", "pass_epa_sum", "rush_plays", "rush_epa_sum",
                "success_sum", "explosive_sum", "dropbacks", "sacks_taken", "int_thrown",
                "fumbles_lost", "fumbles"]
    opp = tg[["game_id", "team"] + off_cols].rename(
        columns={"team": "opp", **{c: f"def_{c}" for c in off_cols}})
    tg = tg.merge(opp, on=["game_id", "opp"], how="left")
    missing = tg.plays.isna().sum()
    if missing:
        raise RuntimeError(f"{missing} team-games have no play-by-play — refusing to continue")
    return tg.sort_values(["season", "week", "game_id", "is_home"]).reset_index(drop=True)


def build_qb_games(games: pd.DataFrame, pbp: pd.DataFrame | None = None) -> pd.DataFrame:
    """Per (game_id, team, passer_player_id): dropbacks, EPA on dropbacks,
    CPOE sum/count. Sacks count as dropbacks with the passer credited."""
    games = normalize_games(games)
    if pbp is None:
        pbp = _load_pbp(sorted(games.season.unique()))
    pbp = pbp[pbp.game_id.isin(set(games.game_id))]
    db = pbp[(pbp.qb_dropback == 1) & pbp.epa.notna() & pbp.passer_player_id.notna()
             & (pbp.qb_spike != 1)].copy()
    db["cpoe_n"] = db.cpoe.notna().astype(int)
    db["cpoe_sum"] = db.cpoe.fillna(0.0)
    qb = db.groupby(["game_id", "posteam", "passer_player_id"]).agg(
        dropbacks=("epa", "size"), epa_sum=("epa", "sum"),
        cpoe_n=("cpoe_n", "sum"), cpoe_sum=("cpoe_sum", "sum"),
    ).reset_index().rename(columns={"posteam": "team", "passer_player_id": "qb_id"})
    meta = games[["game_id", "season", "week", "game_type"]]
    return qb.merge(meta, on="game_id", how="left").sort_values(
        ["season", "week", "game_id", "team", "qb_id"], kind="mergesort").reset_index(drop=True)


if __name__ == "__main__":
    g = nv.load_games(range(2014, 2026))
    tg = build_team_games(g)
    qb = build_qb_games(g)
    print(tg.shape, qb.shape)
    print(tg.head())
    print((tg.epa_sum / tg.plays).describe())
