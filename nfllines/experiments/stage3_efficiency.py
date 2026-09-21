"""Stage 3: efficiency features. (1) tune the tracker's prior blend (n0, carry)
by LOSO; (2) forward-select feature blocks, each gated on LOSO log loss AND
Brier against the previous stage; (3) ridge strength C by LOSO."""
import sys, pathlib, json, time, itertools
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np, pandas as pd
from src.data import nflverse as nv
from src.data.team_games import normalize_games, build_team_games, build_qb_games
from src.features.engine import FeatureEngine
from src.features.efficiency import EfficiencyTracker
from src.models.loso import loso_win, fmt, beats, RidgeLogit

games = normalize_games(nv.feature_frame(nv.load_games(range(2014, 2024)))); games = games[games.home_score.notna()].copy()
tg = build_team_games(games); qbg = build_qb_games(games); players = nv.load_players()
e0 = json.load(open("data/processed/stage0_elo_params.json")); q1 = json.load(open("data/processed/stage1_qb_params.json"))
elo_params = {"k": q1["k"], "hfa": e0["hfa"], "reversion": e0["reversion"]}
qb_params = {"n0": q1["n0"], "decay": q1["decay"]}; scale = q1["qb_elo_scale"]; gi = games.set_index("game_id")
def finish(f):
    f = f[f.season.isin(nv.TRAIN_SEASONS)].copy()
    hs, as_ = gi.loc[f.game_id, "home_score"].to_numpy(), gi.loc[f.game_id, "away_score"].to_numpy()
    f["home_win"] = (hs > as_).astype(int); return f[hs != as_]
def build(n0, carry):
    eng = FeatureEngine(elo_params=elo_params, qb_params=qb_params, qb_elo_scale=scale, players=players,
                        efficiency=EfficiencyTracker(n0=n0, carry=carry))
    return finish(eng.run(games, tg, qbg))

# (1) tracker blend
t = time.time(); rows = []
for n0, carry in itertools.product([2, 4, 6, 9, 13], [0.3, 0.5, 0.7]):
    f = build(n0, carry)
    r = loso_win(f, ["elo_diff", "epa_margin_diff"], C=1.0)
    r2 = loso_win(f, ["epa_margin_diff"], C=1.0)
    rows.append({"n0": n0, "carry": carry, "ll_with_elo": r["log_loss"], "brier_with_elo": r["brier"], "ll_alone": r2["log_loss"]})
res = pd.DataFrame(rows); print(res.sort_values("ll_with_elo").to_string(index=False)); print(f"[{time.time()-t:.0f}s]")
best = res.sort_values("ll_with_elo").iloc[0]; n0, carry = float(best.n0), float(best.carry)
f = build(n0, carry)
f.to_parquet("data/processed/stage3_features_train.parquet", index=False)

base = loso_win(f, ["elo_diff"], C=1.0); print(fmt(base, "Stage 1: QB-adjusted Elo logistic"))
BLOCKS = [
    ("epa", ["epa_margin_diff"]),
    ("epa_split", ["pass_epa_margin_diff", "rush_epa_margin_diff"]),
    ("qb", ["qb_epa_diff"]),
    ("qb_cpoe", ["qb_cpoe_diff"]),
    ("success", ["success_margin_diff"]),
    ("hfa_trend", ["season_idx"]),
    ("neutral", ["neutral"]),
    ("rest", ["rest_diff", "home_off_bye", "away_off_bye", "home_short_week", "away_short_week"]),
    ("sack", ["sack_margin_diff"]),
    ("explosive", ["explosive_margin_diff"]),
    ("turnover", ["turnover_margin_diff"]),
    ("points_vs_epa", ["points_margin_diff"]),
    ("st", ["st_epa_diff"]),
    ("weather", ["wind", "temp", "dome"]),
    ("div", ["div_game"]),
    ("playoff", ["playoff"]),
]
kept = ["elo_diff"]; prev = base; log = []
for name, cols in BLOCKS:
    trial = kept + cols
    r = loso_win(f, trial, C=0.1)
    g = beats(r, prev)
    print(f"+ {name:<14} ll={r['log_loss']:.4f} brier={r['brier']:.4f} acc={r['accuracy']:.3f}  (prev {prev['log_loss']:.4f}/{prev['brier']:.4f})  pass={g['passed']}")
    log.append({"block": name, "cols": cols, "log_loss": r["log_loss"], "brier": r["brier"], "passed": g["passed"]})
    if g["passed"]:
        kept, prev = trial, r
print("KEPT:", kept)
# ridge strength
for C in [0.01, 0.03, 0.1, 0.3, 1.0, 3.0]:
    r = loso_win(f, kept, C=C); print(f"C={C:<5} ll={r['log_loss']:.4f} brier={r['brier']:.4f}")
json.dump({"n0": n0, "carry": carry, "features": kept, "log": log}, open("data/processed/stage3_selection.json", "w"), indent=1)
