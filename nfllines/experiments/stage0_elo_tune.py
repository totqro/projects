"""Stage 0: baselines + Elo constants (K, HFA, reversion) chosen by LOSO."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import itertools, json, sys, time
import numpy as np, pandas as pd
from src.data import nflverse as nv
from src.data.team_games import normalize_games
from src.features.elo import EloEngine, order_games
from src.models.loso import loso_win, score_oof, fmt, folds
from src.models.metrics import log_loss, brier, accuracy

games = order_games(normalize_games(nv.feature_frame(nv.load_games(range(2014, 2024)))))
games = games[games.home_score.notna()].copy()
games["home_win"] = (games.home_score > games.away_score).astype(int)   # ties count as away? see below
ties = (games.home_score == games.away_score).sum()
print("games", len(games), "ties", ties)
train = games.season.isin(nv.TRAIN_SEASONS)

# --- trivial baselines (scored on 2015-2023 only) ----------------------------
y = games.loc[train, "home_win"].to_numpy()
print(f"Always-home: acc={y.mean():.3f}")
oof = np.full(len(games), np.nan)
for s, tr, te in folds(games):
    oof[te.to_numpy()] = games.loc[tr & train, "home_win"].mean()
r = score_oof(games, oof); print(fmt(r, "League-average home win rate (LOSO)"))

# --- Elo grid -----------------------------------------------------------------
def elo_oof(k, hfa, rev, mov=True):
    e = EloEngine(k=k, hfa=hfa, reversion=rev, mov=mov)
    pre = e.run(games)
    return pre.loc[games.game_id, "elo_prob"].to_numpy(), pre.loc[games.game_id, "elo_diff"].to_numpy()

grid = list(itertools.product([10, 15, 20, 25, 30, 40], [20, 35, 48, 55, 65, 80], [0.2, 1/3, 0.5]))
t = time.time()
results = {}
for k, hfa, rev in grid:
    p, d = elo_oof(k, hfa, rev)
    results[(k, hfa, rev)] = p
print(f"grid of {len(grid)} in {time.time()-t:.0f}s")

# per-season log loss table for nested selection
seasons = list(nv.TRAIN_SEASONS)
ll = {key: {s: log_loss(games.loc[games.season == s, "home_win"], p[(games.season == s).to_numpy()])
            for s in seasons} for key, p in results.items()}
# nested LOSO: for each held-out season choose params on the others
nested_oof = np.full(len(games), np.nan); chosen = {}
for s in seasons:
    best = min(ll, key=lambda key: np.mean([ll[key][o] for o in seasons if o != s]))
    chosen[s] = best
    m = (games.season == s).to_numpy()
    nested_oof[m] = results[best][m]
print("nested choices:", chosen)
print(fmt(score_oof(games, nested_oof), "Pure Elo prob, nested-LOSO params"))
overall = min(ll, key=lambda key: np.mean(list(ll[key].values())))
print("best on all of 2015-2023:", overall, "mean ll", np.mean(list(ll[overall].values())))
# show the sensitivity along each axis
for k in [10, 15, 20, 25, 30, 40]:
    print(" K", k, {hfa: round(np.mean(list(ll[(k, hfa, overall[2])].values())), 4) for hfa in [20, 35, 48, 55, 65, 80]})
for rev in [0.2, 1/3, 0.5]:
    print(" rev", round(rev, 3), round(np.mean(list(ll[(overall[0], overall[1], rev)].values())), 4))
p_nomov, _ = elo_oof(*overall, mov=False)
print(fmt(score_oof(games, p_nomov), f"Pure Elo prob, no MOV, params {overall}"))

# --- Elo logistic (the gate baseline) -----------------------------------------
_, d = elo_oof(*overall)
games["elo_diff"] = d
games["elo_prob"] = results[overall]
r = loso_win(games, ["elo_diff"], C=1.0)
print(fmt(r, f"Elo-diff logistic, params {overall}"))
for s, v in r["per_season"].items():
    print(f"   {s}: n={v['n']} ll={v['log_loss']:.4f} brier={v['brier']:.4f} acc={v['accuracy']:.3f}")
json.dump({"k": overall[0], "hfa": overall[1], "reversion": overall[2]}, open("data/processed/stage0_elo_params.json", "w"))
