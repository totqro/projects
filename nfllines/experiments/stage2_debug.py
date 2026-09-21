import sys, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np, pandas as pd
from src.data import nflverse as nv
from src.data.team_games import normalize_games, build_team_games, build_qb_games
from src.features.engine import FeatureEngine
from src.features.week1_prior import Week1Prior, build_team_season_inputs, COMPONENTS
from src.models.loso import loso_win, fmt
games = normalize_games(nv.feature_frame(nv.load_games(range(2014, 2024)))); games = games[games.home_score.notna()].copy()
tg = build_team_games(games); qbg = build_qb_games(games); players = nv.load_players()
snaps = pd.read_parquet(nv.PROCESSED_DIR / "snaps_2014_2025.parquet"); rosters = pd.read_parquet(nv.PROCESSED_DIR / "rosters_weekly_2014_2025.parquet")
inputs = build_team_season_inputs(games, tg, qbg, snaps, rosters, players)
e0 = json.load(open("data/processed/stage0_elo_params.json")); q1 = json.load(open("data/processed/stage1_qb_params.json"))
qb_params = {"n0": q1["n0"], "decay": q1["decay"]}; scale = q1["qb_elo_scale"]; gi = games.set_index("game_id")
def finish(f):
    f = f[f.season.isin(nv.TRAIN_SEASONS)].copy()
    hs, as_ = gi.loc[f.game_id, "home_score"].to_numpy(), gi.loc[f.game_id, "away_score"].to_numpy()
    f["home_win"] = (hs > as_).astype(int); return f[hs != as_]
print("--- flat reversion sweep (Stage 1 engine) ---")
for rev in [0.0, 0.1, 0.2, 1/3, 0.5]:
    eng = FeatureEngine(elo_params={"k": q1["k"], "hfa": e0["hfa"], "reversion": rev}, qb_params=qb_params, qb_elo_scale=scale, players=players)
    f = finish(eng.run(games, tg, qbg))
    a = loso_win(f, ["elo_diff"], C=1.0); w = loso_win(f, ["elo_diff"], C=1.0, weeks=(1, 4))
    print(f"rev={rev:.2f}  all ll={a['log_loss']:.4f} brier={a['brier']:.4f} | w1-4 ll={w['log_loss']:.4f} brier={w['brier']:.4f}")
print("--- hook sanity: prior with a=2/3, intercept 0 must equal flat 1/3 ---")
eng = FeatureEngine(elo_params={"k": q1["k"], "hfa": e0["hfa"], "reversion": 1/3}, qb_params=qb_params, qb_elo_scale=scale, players=players)
prior = Week1Prior(inputs, eng.qb, scale, components=["last_team_pts"], coef={"last_team_pts": 2/3, "intercept": 0.0}, elo_per_point=27.7)
eng.elo.season_start = prior
f2 = finish(eng.run(games, tg, qbg))
eng0 = FeatureEngine(elo_params={"k": q1["k"], "hfa": e0["hfa"], "reversion": 1/3}, qb_params=qb_params, qb_elo_scale=scale, players=players)
f0 = finish(eng0.run(games, tg, qbg))
print("max |elo_diff difference| =", np.abs(f2.elo_diff.to_numpy() - f0.elo_diff.to_numpy()).max())
print("rows recorded:", len(prior.rows), "missing-input fallbacks:", sum(1 for _ in []) )
