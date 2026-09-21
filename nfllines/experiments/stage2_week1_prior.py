"""Stage 2: week-1 prior vs flat reversion, components added one at a time,
gated on LOSO log loss for weeks 1-4 (and reported for the full season)."""
import sys, pathlib, json, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np, pandas as pd
from src.data import nflverse as nv
from src.data.team_games import normalize_games, build_team_games, build_qb_games
from src.features.engine import FeatureEngine
from src.features.week1_prior import Week1Prior, build_team_season_inputs, fit_prior, COMPONENTS
from src.models.loso import loso_win, score_oof, fmt, beats, RidgeLogit

games = normalize_games(nv.feature_frame(nv.load_games(range(2014, 2024))))
games = games[games.home_score.notna()].copy()
tg = build_team_games(games); qbg = build_qb_games(games); players = nv.load_players()
snaps = pd.read_parquet(nv.PROCESSED_DIR / "snaps_2014_2025.parquet")
rosters = pd.read_parquet(nv.PROCESSED_DIR / "rosters_weekly_2014_2025.parquet")
inputs = build_team_season_inputs(games, tg, qbg, snaps, rosters, players)
print("inputs", inputs.shape, "snap_return mean", inputs.snap_return.mean().round(3))
e0 = json.load(open("data/processed/stage0_elo_params.json")); q1 = json.load(open("data/processed/stage1_qb_params.json"))
elo_params = {"k": q1["k"], "hfa": e0["hfa"], "reversion": e0["reversion"]}
qb_params = {"n0": q1["n0"], "decay": q1["decay"]}; scale = q1["qb_elo_scale"]
gi = games.set_index("game_id")

ELO_PER_POINT = None
def make_engine(coef, components):
    eng = FeatureEngine(elo_params=elo_params, qb_params=qb_params, qb_elo_scale=scale, players=players)
    prior = Week1Prior(inputs, eng.qb, scale, components=components, coef=coef, elo_per_point=ELO_PER_POINT)
    eng.elo.season_start = prior
    return eng, prior

def finish(f):
    f = f[f.season.isin(nv.TRAIN_SEASONS)].copy()
    hs, as_ = gi.loc[f.game_id, "home_score"].to_numpy(), gi.loc[f.game_id, "away_score"].to_numpy()
    f["home_win"] = (hs > as_).astype(int); return f[hs != as_]

# measure Elo points per point of margin on the flat-reversion run
ELO_PER_POINT = 25.0
eng, prior = make_engine(None, COMPONENTS)
f_flat = finish(eng.run(games, tg, qbg))
margin = (gi.loc[f_flat.game_id, "home_score"] - gi.loc[f_flat.game_id, "away_score"]).to_numpy()
beta = float(np.sum(margin * f_flat.elo_diff) / np.sum(f_flat.elo_diff ** 2))   # margin ~ beta * elo_diff (no intercept; elo_diff includes HFA)
ELO_PER_POINT = 1.0 / beta
print(f"points per Elo = {beta:.4f} -> elo_per_point = {ELO_PER_POINT:.1f}")
# recording pass (flat reversion) -> fitting table; target = margin minus QB credit
eng, prior = make_engine(None, COMPONENTS)
f_flat = finish(eng.run(games, tg, qbg))
qrows = pd.concat([f_flat[["season", "home_team", "home_qb_epa"]].rename(columns={"home_team": "team", "home_qb_epa": "q"}),
                   f_flat[["season", "away_team", "away_qb_epa"]].rename(columns={"away_team": "team", "away_qb_epa": "q"})])
q_season = qrows.groupby(["team", "season"]).q.mean().rename("q_season").reset_index()
rows = pd.DataFrame(prior.rows); rows = rows[rows.season.isin(nv.TRAIN_SEASONS)].merge(q_season, on=["team", "season"], how="left")
rows["target_team_pts"] = rows.target_margin - (scale / ELO_PER_POINT) * rows.q_season
print("team-season rows", len(rows)); print(rows[COMPONENTS + ["target_margin", "target_team_pts"]].corr()[["target_margin", "target_team_pts"]].round(3))
coef_all = fit_prior(rows, COMPONENTS); print("coef (all 2015-2023):", {k: round(v, 3) for k, v in coef_all.items()})

base_all = loso_win(f_flat, ["elo_diff"], C=1.0); base_w14 = loso_win(f_flat, ["elo_diff"], C=1.0, weeks=(1, 4))
print(fmt(base_all, "Stage 1 flat reversion (all weeks)")); print(fmt(base_w14, "Stage 1 flat reversion (weeks 1-4)"))

def loso_with_prior(components):
    """Per held-out season: fit prior on the other seasons' team-season rows,
    run the engine with those coefficients, keep the held-out season's rows."""
    parts = []
    for s in nv.TRAIN_SEASONS:
        coef = fit_prior(rows[rows.season != s], components)
        eng, _ = make_engine(coef, components)
        f = finish(eng.run(games, tg, qbg)); parts.append(f[f.season == s])
    f = pd.concat(parts)
    # the Elo->prob logistic is itself LOSO inside loso_win
    return f, loso_win(f, ["elo_diff"], C=1.0), loso_win(f, ["elo_diff"], C=1.0, weeks=(1, 4))

prev_all, prev_w14 = base_all, base_w14; kept = []
log = []
for comp in COMPONENTS:
    trial = kept + [comp]
    t = time.time(); f, r_all, r_w14 = loso_with_prior(trial)
    g14 = beats(r_w14, prev_w14); gall = beats(r_all, prev_all)
    print(f"\n+ {comp:<16} weeks1-4: ll={r_w14['log_loss']:.4f} brier={r_w14['brier']:.4f} (prev {prev_w14['log_loss']:.4f}/{prev_w14['brier']:.4f}) "
          f"pass={g14['passed']} | all: ll={r_all['log_loss']:.4f} brier={r_all['brier']:.4f} pass={gall['passed']}  [{time.time()-t:.0f}s]")
    log.append({"component": comp, "w14_ll": r_w14["log_loss"], "w14_brier": r_w14["brier"], "all_ll": r_all["log_loss"], "all_brier": r_all["brier"], "passed_w14": g14["passed"]})
    if g14["passed"]:
        kept.append(comp); prev_all, prev_w14 = r_all, r_w14; f_best = f
    else:
        print(f"  rejected {comp}")
print("\nKEPT:", kept)
coef_final = fit_prior(rows, kept) if kept else None
print("final coef:", coef_final)
json.dump({"components": kept, "coef": coef_final, "log": log}, open("data/processed/stage2_prior.json", "w"), indent=1)
