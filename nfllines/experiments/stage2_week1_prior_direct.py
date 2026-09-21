"""Stage 2 (direct): week-1 prior coefficients chosen by NESTED LOSO log loss
on weeks 1-4 via coordinate descent, one component at a time. For each
held-out season the coefficients (and K) are chosen on the other eight
seasons' out-of-fold weeks 1-4; the held-out season is then scored once."""
import sys, pathlib, json, time, itertools
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np, pandas as pd
from src.data import nflverse as nv
from src.data.team_games import normalize_games, build_team_games, build_qb_games
from src.features.engine import FeatureEngine
from src.features.week1_prior import Week1Prior, build_team_season_inputs, COMPONENTS
from src.models.loso import loso_win, fmt, beats
from src.models.metrics import log_loss, brier

games = normalize_games(nv.feature_frame(nv.load_games(range(2014, 2024)))); games = games[games.home_score.notna()].copy()
tg = build_team_games(games); qbg = build_qb_games(games); players = nv.load_players()
snaps = pd.read_parquet(nv.PROCESSED_DIR / "snaps_2014_2025.parquet"); rosters = pd.read_parquet(nv.PROCESSED_DIR / "rosters_weekly_2014_2025.parquet")
inputs = build_team_season_inputs(games, tg, qbg, snaps, rosters, players)
e0 = json.load(open("data/processed/stage0_elo_params.json")); q1 = json.load(open("data/processed/stage1_qb_params.json"))
qb_params = {"n0": q1["n0"], "decay": q1["decay"]}; scale = q1["qb_elo_scale"]; gi = games.set_index("game_id")
EPP = 27.7
SEASONS = list(nv.TRAIN_SEASONS)

def finish(f):
    f = f[f.season.isin(nv.TRAIN_SEASONS)].copy()
    hs, as_ = gi.loc[f.game_id, "home_score"].to_numpy(), gi.loc[f.game_id, "away_score"].to_numpy()
    f["home_win"] = (hs > as_).astype(int); return f[hs != as_]

cache = {}
def run(coef, k):
    """OOF (LOSO logistic) probabilities for every training game under these prior coefficients."""
    key = (tuple(sorted(coef.items())), k)
    if key in cache: return cache[key]
    eng = FeatureEngine(elo_params={"k": k, "hfa": e0["hfa"], "reversion": e0["reversion"]}, qb_params=qb_params, qb_elo_scale=scale, players=players)
    comps = [c for c in coef if c != "intercept"]
    eng.elo.season_start = Week1Prior(inputs, eng.qb, scale, components=comps, coef=coef, elo_per_point=EPP)
    f = finish(eng.run(games, tg, qbg))
    r = loso_win(f, ["elo_diff"], C=1.0)
    out = f[["game_id", "season", "week", "home_win"]].assign(p=r["oof"])
    cache[key] = out; return out

def score(df, seasons, weeks=(1, 4)):
    m = df.season.isin(seasons) & (df.week >= weeks[0]) & (df.week <= weeks[1])
    return log_loss(df.home_win[m], df.p[m]), brier(df.home_win[m], df.p[m])

GRIDS = {"last_team_pts": [0.5, 0.667, 0.8, 0.9, 1.0, 1.1], "last_epa_margin": [-10, -5, 0, 5, 10, 15, 20],
         "qb_change": [-10, -5, 0, 5, 10], "snap_return": [-4, 0, 4, 8, 12], "coach_change": [-2, -1, 0, 1],
         "intercept": [0.0], "k": [15, 20, 25]}

def coordinate_descent(active, fit_seasons, init):
    """Minimise weeks 1-4 OOF log loss on fit_seasons over the active coefficients (+K)."""
    cur = dict(init); k = cur.pop("k")
    best = score(run(cur, k), fit_seasons)[0]
    for _ in range(2):
        for name in active + ["k"]:
            for v in GRIDS[name]:
                trial = dict(cur); kk = k
                if name == "k": kk = v
                else: trial[name] = v
                s = score(run(trial, kk), fit_seasons)[0]
                if s < best - 1e-6:
                    best, cur, k = s, trial, kk
    cur["k"] = k; return cur, best

# baseline: flat 1/3 reversion, Stage 1 K
base = run({"last_team_pts": 2/3, "intercept": 0.0}, q1["k"])
print("baseline flat reversion: w1-4", score(base, SEASONS), "all", score(base, SEASONS, (1, 22)))

kept, init = [], {"last_team_pts": 2/3, "intercept": 0.0, "k": q1["k"]}
prev_oof = base
log = []
for comp in COMPONENTS:
    active = kept + [comp] if comp != "last_team_pts" else ["last_team_pts"]
    if comp not in init: init[comp] = 0.0
    t = time.time(); oof = base.copy(); chosen = {}
    for s in SEASONS:
        fit_seasons = [o for o in SEASONS if o != s]
        cfg, _ = coordinate_descent(active, fit_seasons, init)
        chosen[s] = cfg
        df = run({k: v for k, v in cfg.items() if k != "k"}, cfg["k"])
        oof.loc[oof.season == s, "p"] = df.loc[df.season == s, "p"].to_numpy()
    w = score(oof, SEASONS); a = score(oof, SEASONS, (1, 22)); pw = score(prev_oof, SEASONS); pa = score(prev_oof, SEASONS, (1, 22))
    passed = w[0] < pw[0] and w[1] < pw[1]
    print(f"+ {comp:<16} w1-4 ll={w[0]:.4f} brier={w[1]:.4f} (prev {pw[0]:.4f}/{pw[1]:.4f}) pass={passed} | all ll={a[0]:.4f} brier={a[1]:.4f} (prev {pa[0]:.4f}/{pa[1]:.4f})  [{time.time()-t:.0f}s]")
    print("   per-fold choices:", {s: {k: v for k, v in c.items() if k in active + ['k']} for s, c in chosen.items()})
    log.append({"component": comp, "w14": w, "all": a, "passed": passed})
    if passed:
        kept.append(comp) if comp != "last_team_pts" else kept.append("last_team_pts")
        prev_oof = oof
        # re-centre init at the all-seasons choice for the next component
        init, _ = coordinate_descent(active, SEASONS, init)
        print("   all-seasons choice:", init)
    else:
        init.pop(comp, None)
print("KEPT:", kept, "final:", init)
json.dump({"components": kept, "coef": {k: v for k, v in init.items() if k != "k"}, "k": init["k"], "elo_per_point": EPP, "log": log},
          open("data/processed/stage2_prior.json", "w"), indent=1)
