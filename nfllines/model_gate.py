"""
Model gate — leave-one-season-out inside 2015-2023, nothing else.
==================================================================
Win model: every block of features is added in tier order and kept only if
it beats the previous stage on BOTH log loss and Brier (pooled out-of-fold
over the nine held-out seasons). Then the ridge strength, then a margin
regression -> Normal win probability, then the logit/margin blend, each by
the same rule. The result is written to ml_models/win_model.json.

Points model: ridge on two team-game rows per game, gated against the
league-average-plus-home-adjustment baseline on LOSO RMSE and MAE for home
points, away points, margin and total. Written to ml_models/points_model.json
only if it passes.

    python model_gate.py             # win model gate + points gate
    python model_gate.py --ablation  # drop each kept block from the final set
"""
import argparse
import json
import warnings

import numpy as np
import pandas as pd

from src.data import nflverse as nv
from src.models.loso import loso_win, loso_reg, beats, fmt, score_oof
from src.models.metrics import log_loss, brier, win_metrics
from src.models.points_model import (PointsModel, TEAM_FEATURES, loso_points,
                                     loso_baseline, beats_points)
from src.models.win_model import WinModel, WIN_MODEL_PATH, POINTS_MODEL_PATH
from scipy.stats import norm

warnings.filterwarnings("ignore")

FEATURES_PATH = nv.PROCESSED_DIR / "features.parquet"
RESULTS_PATH = nv.PROCESSED_DIR / "gate_results.json"

# Forward-selection blocks in tier order (README "Stage 3"). Elo is the seed.
BLOCKS = [
    # tier 1
    ("qb_rating", ["qb_epa_diff"]),
    ("qb_cpoe", ["qb_cpoe_diff"]),
    ("epa", ["epa_margin_diff"]),
    ("epa_pass_rush", ["pass_epa_margin_diff", "rush_epa_margin_diff"]),
    ("success", ["success_margin_diff"]),
    ("hfa_trend", ["season_idx"]),
    ("neutral", ["neutral"]),
    ("rest", ["rest_diff", "home_off_bye", "away_off_bye", "home_short_week", "away_short_week"]),
    ("week1_prior_early", ["prior_last_team_pts_early_diff", "prior_snap_return_early_diff"]),
    ("week1_prior_epa_early", ["prior_last_epa_early_diff"]),
    ("week1_prior_coach_early", ["prior_coach_change_early_diff"]),
    # tier 2
    ("sack", ["sack_margin_diff"]),
    ("explosive", ["explosive_margin_diff"]),
    ("turnover_luck", ["turnover_margin_diff"]),
    ("points_vs_epa", ["points_margin_diff"]),
    ("special_teams", ["st_epa_diff"]),
    # tier 3
    ("weather", ["wind", "temp", "dome"]),
    ("division", ["div_game"]),
    ("playoff", ["playoff"]),
    # stage 4
    ("injuries", ["inj_total_diff"]),
    ("injuries_OL_cluster", ["inj_OL_starters_diff"]),
]


def load_train() -> pd.DataFrame:
    df = pd.read_parquet(FEATURES_PATH)
    df = df[df.season.isin(nv.TRAIN_SEASONS)].copy()
    return df


def win_gate(df: pd.DataFrame, verbose: bool = True) -> dict:
    d = df[df.home_win.notna()].copy()
    d["home_win"] = d.home_win.astype(int)
    out = {"baselines": {}, "selection": [], "kept": None}

    # baselines
    oof = np.full(len(d), np.nan)
    for s in nv.TRAIN_SEASONS:
        oof[(d.season == s).to_numpy()] = d.loc[d.season != s, "home_win"].mean()
    r = score_oof(d, oof); r.pop("oof"); out["baselines"]["home_rate"] = r
    r0 = loso_win(d, ["elo0_diff"], C=1.0); r0.pop("oof"); out["baselines"]["stage0_elo"] = r0
    r1 = loso_win(d, ["elo_diff"], C=1.0); r1.pop("oof"); out["baselines"]["stage1_qb_elo"] = r1
    if verbose:
        print(fmt(r, "League-average home win rate"))
        print(fmt(r0, "Stage 0: Elo (K=20, HFA, MOV) logistic"))
        print(fmt(r1, "Stage 1: QB-adjusted Elo logistic"))
        print("-" * 100)

    kept = ["elo_diff"]; prev = r1; C = 0.1
    for name, cols in BLOCKS:
        trial = kept + cols
        r = loso_win(d, trial, C=C); r.pop("oof")
        g = beats(r, prev)
        out["selection"].append({"block": name, "cols": cols, **{k: r[k] for k in ("log_loss", "brier", "accuracy")}, **g})
        if verbose:
            print(f"+ {name:<24} ll={r['log_loss']:.4f} brier={r['brier']:.4f} acc={r['accuracy']:.3f}  "
                  f"(prev {prev['log_loss']:.4f}/{prev['brier']:.4f})  {'KEEP' if g['passed'] else 'reject'}")
        if g["passed"]:
            kept, prev = trial, r
    if verbose:
        print("-" * 100); print("kept:", kept)

    # ridge strength
    best_C, best = C, prev
    for c in [0.01, 0.03, 0.1, 0.3, 1.0, 3.0]:
        r = loso_win(d, kept, C=c); r.pop("oof")
        if verbose:
            print(f"C={c:<5} ll={r['log_loss']:.4f} brier={r['brier']:.4f}")
        if c != C and beats(r, best)["passed"]:
            best_C, best = c, r
    if verbose:
        print("C chosen:", best_C)
    r_logit = loso_win(d, kept, C=best_C)
    p_logit = r_logit["oof"]

    # margin regression -> Normal win prob
    margin_res = {}
    best_alpha, best_m = None, None
    for alpha in [1, 3, 10, 30, 100]:
        rm = loso_reg(d, kept, "margin", alpha=alpha)
        margin_res[alpha] = rm["rmse"]
        if best_m is None or rm["rmse"] < best_m["rmse"]:
            best_alpha, best_m = alpha, rm
    sigma = float(np.std(d.margin.to_numpy() - best_m["oof"]))
    p_margin = norm.cdf(best_m["oof"] / sigma)
    r_margin = score_oof(d, p_margin); r_margin.pop("oof")
    if verbose:
        print(f"margin ridge alpha={best_alpha} LOSO rmse={best_m['rmse']:.3f} sigma={sigma:.2f}")
        print(fmt(r_margin, "Normal(margin/sigma) win prob"))
    blends = {}
    for b in [0.0, 0.25, 0.5, 0.75, 1.0]:
        rb = score_oof(d, (1 - b) * p_logit + b * p_margin); rb.pop("oof")
        blends[b] = rb
        if verbose:
            print(f"blend {b:.2f}: ll={rb['log_loss']:.4f} brier={rb['brier']:.4f} acc={rb['accuracy']:.3f}")
    base_b = blends[0.0]; chosen_b = 0.0
    for b in [0.25, 0.5, 0.75, 1.0]:
        if beats(blends[b], blends[chosen_b])["passed"]:
            chosen_b = b
    final = blends[chosen_b]
    p_final = (1 - chosen_b) * p_logit + chosen_b * p_margin
    agree = float(np.mean((p_final > 0.5) == (best_m["oof"] > 0)))
    if verbose:
        print(f"blend chosen: {chosen_b}  ->  {fmt(final, 'FINAL win model (LOSO)')}")
        print(f"favourite agreement, shipped p vs shipped margin: {agree:.3f}")
        for s, v in final["per_season"].items():
            print(f"   {s}: ll={v['log_loss']:.4f} (elo0 {r0['per_season'][s]['log_loss']:.4f})  brier={v['brier']:.4f}  acc={v['accuracy']:.3f}")

    out.update({"kept": kept, "C": best_C, "alpha": best_alpha, "sigma": sigma, "blend": chosen_b,
                "logit": {k: r_logit[k] for k in ("log_loss", "brier", "accuracy", "ece")},
                "margin_normal": r_margin, "blends": {str(k): {kk: v[kk] for kk in ("log_loss", "brier")} for k, v in blends.items()},
                "final": final, "favourite_agreement": agree,
                "margin_rmse_by_alpha": margin_res})
    # persist the OOF predictions for calibrate.py
    oofdf = d[["game_id", "season", "week", "home_win"]].copy()
    oofdf["p_oof"] = p_final; oofdf["margin_oof"] = best_m["oof"]
    oofdf.to_parquet(nv.PROCESSED_DIR / "win_oof.parquet", index=False)
    return out


def ablation(df: pd.DataFrame, gate: dict) -> list:
    d = df[df.home_win.notna()].copy(); d["home_win"] = d.home_win.astype(int)
    kept, C = gate["kept"], gate["C"]
    full = loso_win(d, kept, C=C); full.pop("oof")
    print(fmt(full, "full kept set"))
    rows = []
    blocks = [("elo", ["elo_diff"])] + [(n, c) for n, c in BLOCKS if all(x in kept for x in c)]
    for name, cols in blocks:
        sub = [c for c in kept if c not in cols]
        if not sub:
            continue
        r = loso_win(d, sub, C=C); r.pop("oof")
        rows.append({"dropped": name, "log_loss": r["log_loss"], "brier": r["brier"]})
        print(f"- {name:<24} ll={r['log_loss']:.4f} brier={r['brier']:.4f}  (delta ll {r['log_loss']-full['log_loss']:+.4f})")
    return rows


def points_gate(df: pd.DataFrame, verbose: bool = True) -> dict:
    base = loso_baseline(df)
    if verbose:
        print("Points baseline (league avg + home adj):",
              {k: round(v, 3) for k, v in base.items() if k != "game_level"})
    best_alpha, best = None, None
    for alpha in [1, 3, 10, 30, 100, 300, 1000, 3000]:
        r = loso_points(df, TEAM_FEATURES, alpha=alpha)
        if verbose:
            print(f"ridge alpha={alpha:<4} home rmse={r['home_rmse']:.3f} mae={r['home_mae']:.3f} | margin rmse={r['margin_rmse']:.3f} "
                  f"mae={r['margin_mae']:.3f} | total rmse={r['total_rmse']:.3f} mae={r['total_mae']:.3f}")
        if best is None or r["margin_rmse"] + r["total_rmse"] < best["margin_rmse"] + best["total_rmse"]:
            best_alpha, best = alpha, r
    g = beats_points(best, base)
    if verbose:
        print("gate (rmse AND mae, each target):", g)
    out = {"baseline": {k: v for k, v in base.items() if k != "game_level"},
           "candidate": {k: v for k, v in best.items() if k != "game_level"}, "alpha": best_alpha, "gate": g}
    best["game_level"][["pred_home", "pred_away", "pred_margin", "pred_total"]].to_parquet(
        nv.PROCESSED_DIR / "points_oof.parquet")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ablation", action="store_true")
    ap.add_argument("--no-points", action="store_true")
    args = ap.parse_args()
    df = load_train()
    print("=" * 100); print("  WIN MODEL GATE (LOSO 2015-2023)"); print("=" * 100)
    gate = win_gate(df)
    results = {"win": gate}
    if args.ablation:
        print("=" * 100); print("  ABLATION"); print("=" * 100)
        results["ablation"] = ablation(df, gate)
    if not args.no_points:
        print("=" * 100); print("  POINTS MODEL GATE"); print("=" * 100)
        results["points"] = points_gate(df)
    # persist chosen models, fit on all of 2015-2023
    wm = WinModel(gate["kept"], C=gate["C"], alpha=gate["alpha"], blend=gate["blend"], sigma=gate["sigma"]).fit(df)
    wm.save(WIN_MODEL_PATH); print("wrote", WIN_MODEL_PATH)
    if not args.no_points and results["points"]["gate"]["passed"]:
        pm = PointsModel(TEAM_FEATURES, alpha=results["points"]["alpha"]).fit(df)
        POINTS_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        json.dump(pm.to_dict(), open(POINTS_MODEL_PATH, "w"), indent=1); print("wrote", POINTS_MODEL_PATH)
    elif not args.no_points:
        print("points model did NOT pass the gate — nothing written; league-average baseline stands")
    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=1, default=lambda o: float(o) if isinstance(o, (np.floating,)) else str(o))
    print("wrote", RESULTS_PATH)


if __name__ == "__main__":
    main()
