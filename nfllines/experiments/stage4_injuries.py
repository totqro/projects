"""Stage 4: injury adjustments (contract/draft value x P(miss) - missed share,
by position group) gated on top of the Stage 3 features."""
import sys, pathlib, json, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np, pandas as pd
from src.data import nflverse as nv
from src.data.team_games import normalize_games, build_team_games, build_qb_games
from src.data.injury_context import build_context, GROUPS
from src.features.engine import FeatureEngine
from src.features.efficiency import EWMATracker
from src.features.injuries import InjuryTracker
from src.models.loso import loso_win, fmt, beats
games = normalize_games(nv.feature_frame(nv.load_games(range(2014, 2024)))); games = games[games.home_score.notna()].copy()
tg = build_team_games(games); qbg = build_qb_games(games); players = nv.load_players()
ctx = build_context(range(2014, 2024), games)
e0 = json.load(open("data/processed/stage0_elo_params.json")); q1 = json.load(open("data/processed/stage1_qb_params.json"))
elo_params = {"k": q1["k"], "hfa": e0["hfa"], "reversion": e0["reversion"]}; qb_params = {"n0": q1["n0"], "decay": q1["decay"]}; scale = q1["qb_elo_scale"]
gi = games.set_index("game_id")
def finish(f):
    f = f[f.season.isin(nv.TRAIN_SEASONS)].copy()
    hs, as_ = gi.loc[f.game_id, "home_score"].to_numpy(), gi.loc[f.game_id, "away_score"].to_numpy()
    f["home_win"] = (hs > as_).astype(int); return f[hs != as_]
BASE = ["elo_diff", "success_margin_diff", "st_epa_diff"]
for dw, window in [(0.03, 8), (0.0, 8), (0.1, 8), (0.03, 4), (0.03, 12)]:
    t = time.time()
    eng = FeatureEngine(elo_params=elo_params, qb_params=qb_params, qb_elo_scale=scale, players=players,
                        efficiency=EWMATracker(), injuries=InjuryTracker(ctx, draft_weight=dw, window=window))
    f = finish(eng.run(games, tg, qbg, context=ctx))
    base = loso_win(f, BASE, C=0.1)
    r_tot = loso_win(f, BASE + ["inj_total_diff"], C=0.1)
    r_grp = loso_win(f, BASE + [f"inj_{g}_diff" for g in GROUPS], C=0.1)
    r_ol = loso_win(f, BASE + ["inj_total_diff", "inj_OL_starters_diff"], C=0.1)
    print(f"draft_weight={dw} window={window}  [{time.time()-t:.0f}s]  base ll={base['log_loss']:.4f}/{base['brier']:.4f}")
    for name, r in [("inj_total", r_tot), ("inj_by_group", r_grp), ("inj_total+OL", r_ol)]:
        g = beats(r, base); print(f"   {name:<14} ll={r['log_loss']:.4f} brier={r['brier']:.4f} pass={g['passed']}")
    if dw == 0.03 and window == 8:
        f.to_parquet("data/processed/stage4_features_train.parquet", index=False)
        print("   inj_total_diff describe:", f.inj_total_diff.describe().round(4).to_dict())
        # margin regression check: points of margin per unit of inj_total_diff
        margin = (gi.loc[f.game_id, "home_score"] - gi.loc[f.game_id, "away_score"]).to_numpy()
        X = np.c_[np.ones(len(f)), f.elo_diff, f.inj_total_diff]; b = np.linalg.lstsq(X, margin, rcond=None)[0]
        print("   margin ~ elo_diff + inj_total_diff:", b.round(4), " corr(inj_total_diff, margin - elo part) =",
              np.corrcoef(f.inj_total_diff, margin - b[1]*f.elo_diff)[0,1].round(4))
