"""Stage 2c: the week-1 prior (full carry + snap_return) together with an
early-season K boost, so the prior can carry information into weeks 1-4
without anchoring the rest of the season. Nested LOSO as in stage2_direct."""
import sys, pathlib, json, time, itertools
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np, pandas as pd
from src.data import nflverse as nv
from src.data.team_games import normalize_games, build_team_games, build_qb_games
from src.features.engine import FeatureEngine
from src.features.week1_prior import Week1Prior, build_team_season_inputs
from src.models.loso import loso_win
from src.models.metrics import log_loss, brier
games = normalize_games(nv.feature_frame(nv.load_games(range(2014, 2024)))); games = games[games.home_score.notna()].copy()
tg = build_team_games(games); qbg = build_qb_games(games); players = nv.load_players()
snaps = pd.read_parquet(nv.PROCESSED_DIR / "snaps_2014_2025.parquet"); rosters = pd.read_parquet(nv.PROCESSED_DIR / "rosters_weekly_2014_2025.parquet")
inputs = build_team_season_inputs(games, tg, qbg, snaps, rosters, players)
e0 = json.load(open("data/processed/stage0_elo_params.json")); q1 = json.load(open("data/processed/stage1_qb_params.json"))
qb_params = {"n0": q1["n0"], "decay": q1["decay"]}; scale = q1["qb_elo_scale"]; gi = games.set_index("game_id"); EPP = 27.7; SEASONS = list(nv.TRAIN_SEASONS)
def finish(f):
    f = f[f.season.isin(nv.TRAIN_SEASONS)].copy()
    hs, as_ = gi.loc[f.game_id, "home_score"].to_numpy(), gi.loc[f.game_id, "away_score"].to_numpy()
    f["home_win"] = (hs > as_).astype(int); return f[hs != as_]
cache = {}
def run(cfg):
    key = tuple(sorted(cfg.items()))
    if key in cache: return cache[key]
    eng = FeatureEngine(elo_params={"k": cfg["k"], "hfa": e0["hfa"], "reversion": cfg["rev"], "k_early_mult": cfg["kmult"], "k_early_games": cfg["kgames"]},
                        qb_params=qb_params, qb_elo_scale=scale, players=players)
    if cfg["prior"]:
        coef = {"last_team_pts": cfg["a"], "snap_return": cfg["snap"], "intercept": 0.0}
        eng.elo.season_start = Week1Prior(inputs, eng.qb, scale, components=["last_team_pts", "snap_return"], coef=coef, elo_per_point=EPP)
    f = finish(eng.run(games, tg, qbg)); r = loso_win(f, ["elo_diff"], C=1.0)
    out = f[["game_id", "season", "week", "home_win"]].assign(p=r["oof"]); cache[key] = out; return out
def score(df, seasons, weeks=(1, 4)):
    m = df.season.isin(seasons) & (df.week >= weeks[0]) & (df.week <= weeks[1]); return log_loss(df.home_win[m], df.p[m]), brier(df.home_win[m], df.p[m])
GRIDS = {"a": [0.8, 0.9, 1.0, 1.1, 1.2], "snap": [0, 4, 8, 12], "k": [15, 20, 25], "kmult": [1.0, 1.5, 2.0, 2.5], "kgames": [2, 4, 6]}
def cd(fit_seasons, init, objective_weeks):
    cur = dict(init); best = score(run(cur), fit_seasons, objective_weeks)[0]
    for _ in range(2):
        for name, vals in GRIDS.items():
            for v in vals:
                t = dict(cur); t[name] = v; s = score(run(t), fit_seasons, objective_weeks)[0]
                if s < best - 1e-6: best, cur = s, t
    return cur
base_cfg = {"prior": False, "a": 0, "snap": 0, "k": q1["k"], "rev": e0["reversion"], "kmult": 1.0, "kgames": 0}
base = run(base_cfg); print("baseline flat: w1-4", score(base, SEASONS), "all", score(base, SEASONS, (1, 22)), flush=True)
for objective in [(1, 4), (1, 22)]:
    init = {"prior": True, "a": 1.0, "snap": 8, "k": 20, "rev": 0.0, "kmult": 1.5, "kgames": 4}
    oof = base.copy(); chosen = {}
    for s in SEASONS:
        cfg = cd([o for o in SEASONS if o != s], init, objective); chosen[s] = cfg
        df = run(cfg); oof.loc[oof.season == s, "p"] = df.loc[df.season == s, "p"].to_numpy()
    w, a = score(oof, SEASONS), score(oof, SEASONS, (1, 22))
    print(f"objective weeks {objective}: nested OOF  w1-4 ll={w[0]:.4f} brier={w[1]:.4f} | all ll={a[0]:.4f} brier={a[1]:.4f}", flush=True)
    print("  per-fold:", {s: {k: v for k, v in c.items() if k in GRIDS} for s, c in chosen.items()}, flush=True)
    final = cd(SEASONS, init, objective); print("  all-seasons choice:", final, flush=True)
    json.dump(final, open(f"data/processed/stage2c_choice_w{objective[1]}.json", "w"))
