import sys, pathlib, json, itertools, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np, pandas as pd
from src.data import nflverse as nv
from src.data.team_games import normalize_games, build_team_games, build_qb_games
from src.features.engine import FeatureEngine
from src.models.loso import loso_win, fmt, beats

games = normalize_games(nv.feature_frame(nv.load_games(range(2014, 2024))))
games = games[games.home_score.notna()].copy()
tg = build_team_games(games); qbg = build_qb_games(games); players = nv.load_players()
elo_params = json.load(open("data/processed/stage0_elo_params.json"))
gi = games.set_index("game_id")
def run(scale, n0, decay, k=None, hfa=None):
    ep = dict(elo_params); 
    if k: ep["k"] = k
    if hfa: ep["hfa"] = hfa
    eng = FeatureEngine(elo_params=ep, qb_params={"n0": n0, "decay": decay}, qb_elo_scale=scale, players=players)
    f = eng.run(games, tg, qbg); f = f[f.season.isin(nv.TRAIN_SEASONS)].copy()
    hs, as_ = gi.loc[f.game_id, "home_score"].to_numpy(), gi.loc[f.game_id, "away_score"].to_numpy()
    f["home_win"] = (hs > as_).astype(int); return f[hs != as_]
rows = []
for scale, n0, decay, k in itertools.product([400, 500, 600, 800, 1000], [200, 400], [0.8, 0.9], [15, 20, 25]):
    f = run(scale, n0, decay, k=k)
    r = loso_win(f, ["elo_diff"], C=1.0); r2 = loso_win(f, ["elo_diff", "qb_epa_diff"], C=1.0)
    rows.append({"scale": scale, "n0": n0, "decay": decay, "k": k, "ll": r["log_loss"], "brier": r["brier"],
                 "ll_plus_qbfeat": r2["log_loss"], "brier_plus": r2["brier"]})
res = pd.DataFrame(rows)
print(res.sort_values("ll").head(10).to_string(index=False))
print(res.sort_values("ll_plus_qbfeat").head(6).to_string(index=False))
print(res.groupby("scale")[["ll", "ll_plus_qbfeat"]].mean().round(4))
print(res.groupby("k")[["ll", "ll_plus_qbfeat"]].mean().round(4))
best = res.sort_values("ll").iloc[0]
json.dump({"qb_elo_scale": float(best.scale), "n0": float(best.n0), "decay": float(best.decay), "k": int(best.k)},
          open("data/processed/stage1_qb_params.json", "w"))
print("saved", best.to_dict())
