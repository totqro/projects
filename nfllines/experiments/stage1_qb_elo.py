"""Stage 1: QB-adjusted Elo. Grid over the Elo-points-per-EPA scale and the
QB shrinkage constants, LOSO on 2015-2023, gated against Stage 0 Elo."""
import sys, pathlib, json, itertools, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np, pandas as pd
from src.data import nflverse as nv
from src.data.team_games import normalize_games, build_team_games, build_qb_games
from src.features.engine import FeatureEngine
from src.models.loso import loso_win, score_oof, fmt, beats

games = normalize_games(nv.feature_frame(nv.load_games(range(2014, 2024))))
games = games[games.home_score.notna()].copy()
tg = build_team_games(games); qbg = build_qb_games(games)
players = nv.load_players()
elo_params = json.load(open("data/processed/stage0_elo_params.json"))

def run(scale, n0, decay):
    eng = FeatureEngine(elo_params=elo_params, qb_params={"n0": n0, "decay": decay},
                        qb_elo_scale=scale, players=players)
    f = eng.run(games, tg, qbg)
    f = f[f.season.isin(nv.TRAIN_SEASONS)].copy()
    f["home_win"] = (games.set_index("game_id").loc[f.game_id, "home_score"].to_numpy()
                     > games.set_index("game_id").loc[f.game_id, "away_score"].to_numpy()).astype(int)
    tie = (games.set_index("game_id").loc[f.game_id, "home_score"].to_numpy()
           == games.set_index("game_id").loc[f.game_id, "away_score"].to_numpy())
    f = f[~tie]
    return f

base = run(0.0, 700, 0.6)
r0 = loso_win(base, ["elo_diff"], C=1.0)
print(fmt(r0, "Stage 0: Elo logistic"))
r0b = loso_win(base, ["elo_diff", "qb_epa_diff"], C=1.0)
print(fmt(r0b, "Elo + qb_epa_diff as separate feature (n0=700, d=0.6)"), beats(r0b, r0)["passed"])

t = time.time()
rows = []
for scale, n0, decay in itertools.product([100, 150, 200, 250, 300, 400], [400, 700, 1000], [0.4, 0.6, 0.8]):
    f = run(scale, n0, decay)
    r = loso_win(f, ["elo_diff"], C=1.0)
    rows.append({"scale": scale, "n0": n0, "decay": decay, "log_loss": r["log_loss"], "brier": r["brier"], "acc": r["accuracy"]})
res = pd.DataFrame(rows).sort_values("log_loss")
print(f"grid in {time.time()-t:.0f}s"); print(res.head(12).to_string(index=False))
print(res.groupby("scale")[["log_loss","brier"]].mean().round(4))
best = res.iloc[0]
f = run(best.scale, best.n0, best.decay)
r1 = loso_win(f, ["elo_diff"], C=1.0)
print(fmt(r1, f"Stage 1: QB-adjusted Elo (scale={best.scale:.0f}, n0={best.n0:.0f}, decay={best.decay})"))
print("gate vs Stage 0:", beats(r1, r0))
for s, v in r1["per_season"].items():
    print(f"   {s}: ll={v['log_loss']:.4f} (stage0 {r0['per_season'][s]['log_loss']:.4f}) brier={v['brier']:.4f}")
# magnitude: Elo points per EPA/db -> points of margin (25 Elo ~ 1 pt): elite (+0.20) vs backup (-0.12)
print(f"implied swing elite(+0.20)->backup(-0.12): {best.scale*0.32/25:.1f} points")
json.dump({"qb_elo_scale": float(best.scale), "n0": float(best.n0), "decay": float(best.decay)},
          open("data/processed/stage1_qb_params.json", "w"))
