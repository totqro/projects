"""Assemble the engine with the frozen config and build the feature table."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src import config as C
from src.data import nflverse as nv
from src.data.injury_context import build_context
from src.data.team_games import normalize_games, build_team_games, build_qb_games
from src.features.efficiency import EWMATracker
from src.features.engine import FeatureEngine
from src.features.injuries import InjuryTracker
from src.features.week1_prior import Week1Prior, build_team_season_inputs

# Columns that are identifiers / targets, not features.
ID_COLUMNS = ["game_id", "season", "week", "game_type", "home_team", "away_team"]
TARGET_COLUMNS = ["home_score", "away_score", "home_win", "margin", "total", "tie"]


def load_inputs(seasons):
    """Everything the engine walks over, with market columns already gone."""
    games_all = nv.load_games(seasons)
    market = games_all[["game_id"] + [c for c in nv.MARKET_COLUMNS if c in games_all.columns]].copy()
    games = normalize_games(nv.feature_frame(games_all))
    tg = build_team_games(games[games.home_score.notna()])
    qbg = build_qb_games(games[games.home_score.notna()])
    players = nv.load_players()
    snaps = nv.cached_seasons("snaps", nv.load_snap_counts, seasons)
    rosters = nv.cached_seasons("rosters_weekly", nv.load_rosters_weekly, seasons)
    prior_inputs = build_team_season_inputs(games, tg, qbg, snaps, rosters, players)
    ctx = build_context(seasons, games)
    return {"games": games, "team_games": tg, "qb_games": qbg, "players": players,
            "prior_inputs": prior_inputs, "context": ctx, "market": market}


def make_engine(inputs: dict) -> FeatureEngine:
    eng = FeatureEngine(
        elo_params={"k": C.ELO_K, "hfa": C.ELO_HFA, "reversion": C.ELO_REVERSION},
        qb_params={"n0": C.QB_N0, "decay": C.QB_DECAY},
        qb_elo_scale=C.QB_ELO_SCALE, players=inputs["players"],
        efficiency=EWMATracker(lam=C.EFF_LAMBDA, season_discount=C.EFF_SEASON_DISCOUNT, n0=C.EFF_N0),
        injuries=InjuryTracker(inputs["context"], draft_weight=C.INJ_DRAFT_WEIGHT, window=C.INJ_WINDOW),
    )
    # feature mode: coef=None -> Elo keeps flat reversion, inputs are emitted as features
    prior = Week1Prior(inputs["prior_inputs"], eng.qb, C.QB_ELO_SCALE, coef=None, elo_per_point=C.ELO_PER_POINT)
    eng.week1_prior = prior
    eng.elo.season_start = prior
    return eng


def attach_targets(features: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    gi = games.set_index("game_id")
    f = features.copy()
    f["home_score"] = gi.loc[f.game_id, "home_score"].to_numpy()
    f["away_score"] = gi.loc[f.game_id, "away_score"].to_numpy()
    f["margin"] = f.home_score - f.away_score
    f["total"] = f.home_score + f.away_score
    f["tie"] = (f.margin == 0).astype(float)
    f["home_win"] = np.where(f.margin > 0, 1.0, np.where(f.margin < 0, 0.0, np.nan))
    return f


def plain_elo(games: pd.DataFrame) -> pd.DataFrame:
    """Stage 0 Elo (no QB split) — the gate baseline, as two extra columns."""
    from src.features.elo import EloEngine, order_games
    eng = EloEngine(k=C.ELO_K_STAGE0, hfa=C.ELO_HFA, reversion=C.ELO_REVERSION)
    pre = eng.run(order_games(games))
    return pre[["elo_diff", "elo_prob"]].rename(columns={"elo_diff": "elo0_diff", "elo_prob": "elo0_prob"})


def build_features(seasons=nv.ALL_SEASONS, inputs: dict | None = None) -> tuple[pd.DataFrame, dict]:
    inputs = inputs or load_inputs(seasons)
    eng = make_engine(inputs)
    feats = eng.run(inputs["games"], inputs["team_games"], inputs["qb_games"], context=inputs["context"])
    e0 = plain_elo(inputs["games"])
    feats["elo0_diff"] = e0.loc[feats.game_id, "elo0_diff"].to_numpy()
    feats["elo0_prob"] = e0.loc[feats.game_id, "elo0_prob"].to_numpy()
    return attach_targets(feats, inputs["games"]), inputs


def serve_features(inputs: dict, game_id: str) -> dict:
    """The serving path: a fresh engine walked over every week strictly
    before this game's week, then features_for(game). Used by the
    recomputation test and by any live prediction."""
    games = inputs["games"]
    g = games[games.game_id == game_id].iloc[0]
    eng = make_engine(inputs)
    eng.run(games, inputs["team_games"], inputs["qb_games"], context=inputs["context"],
            stop_before=(int(g.season), int(g.week)), emit=False)
    if eng.efficiency is not None:
        eng.efficiency.start_week(int(g.season), int(g.week))
    if eng.injuries is not None:
        eng.injuries.start_week(int(g.season), int(g.week), inputs["context"])
    f = eng.features_for(g)
    e0 = plain_elo(games[(games.season < g.season) | ((games.season == g.season) & (games.week <= g.week))])
    f["elo0_diff"] = float(e0.loc[game_id, "elo0_diff"])
    f["elo0_prob"] = float(e0.loc[game_id, "elo0_prob"])
    return f


def feature_columns(df: pd.DataFrame) -> list:
    return [c for c in df.columns if c not in ID_COLUMNS + TARGET_COLUMNS]
