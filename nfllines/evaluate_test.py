"""
The one-time evaluation on the 2024-2025 test seasons.
=======================================================
Fits the frozen win model (ml_models/win_model.json: features, C, blend,
sigma, calibrator — all chosen by LOSO inside 2015-2023) and the frozen
points model on 2015-2023, predicts every 2024-2025 game from the same
point-in-time feature table, and scores model vs Elo baseline vs market.

Market benchmark: de-vigged closing moneylines (nflverse schedule
`home_moneyline` / `away_moneyline`); where a moneyline is missing the
spread is converted through the fitted sigma, and the count is reported.
Points benchmark: closing spread (`spread_line`, positive = home favoured)
for margin, closing total for total, implied team totals
(total/2 +- spread/2) for team points. The market columns are read here and
nowhere else.

This script is meant to run ONCE. It writes data/processed/TEST_EVALUATED
and refuses to run again without --force; if you find yourself wanting to
iterate after seeing these numbers, stop and report instead.

    python evaluate_test.py
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

from src.data import nflverse as nv
from src.models.loso import RidgeLogit
from src.models.metrics import win_metrics, reliability_table, bootstrap_gap, log_loss, brier, rmse, mae
from src.models.points_model import PointsModel, team_rows
from src.models.win_model import WinModel, WIN_MODEL_PATH, POINTS_MODEL_PATH

MARKER = nv.PROCESSED_DIR / "TEST_EVALUATED"
OUT = nv.PROCESSED_DIR / "test_evaluation.json"


def american_to_prob(ml):
    ml = np.asarray(ml, dtype=float)
    return np.where(ml < 0, -ml / (-ml + 100.0), 100.0 / (ml + 100.0))


def market_probs(m: pd.DataFrame, sigma: float) -> tuple[np.ndarray, int]:
    ph, pa = american_to_prob(m.home_moneyline), american_to_prob(m.away_moneyline)
    p = ph / (ph + pa)
    missing = np.isnan(p)
    p = np.where(missing, norm.cdf(m.spread_line.to_numpy(float) / sigma), p)
    return p, int(missing.sum())


def qb_change_flags(test_ids: pd.Series) -> pd.Series:
    """Games where either starter differs from that team's previous game's
    starter (the schedule's actual-starter columns, see README caveat)."""
    g = nv.load_games(nv.ALL_SEASONS)
    from src.data.team_games import normalize_games
    g = normalize_games(g)
    g = g.sort_values(["season", "week"])
    rows = pd.concat([
        g[["game_id", "season", "week", "home_team", "home_qb_id"]].rename(columns={"home_team": "team", "home_qb_id": "qb"}),
        g[["game_id", "season", "week", "away_team", "away_qb_id"]].rename(columns={"away_team": "team", "away_qb_id": "qb"}),
    ]).sort_values(["team", "season", "week"])
    rows["prev_qb"] = rows.groupby("team").qb.shift(1)
    rows["changed"] = (rows.qb != rows.prev_qb) & rows.prev_qb.notna()
    flag = rows.groupby("game_id").changed.max()
    return test_ids.map(flag).fillna(False).astype(bool)


def block(y, preds: dict, label: str) -> dict:
    out = {}
    for name, p in preds.items():
        out[name] = win_metrics(y, p)
    print(f"\n{label}  (n={len(y)})")
    print(f"{'':<12}{'logloss':>9}{'brier':>8}{'acc':>7}{'ece':>7}")
    for name, r in out.items():
        print(f"{name:<12}{r['log_loss']:>9.4f}{r['brier']:>8.4f}{r['accuracy']:>7.3f}{r['ece']:>7.4f}")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if MARKER.exists() and not args.force:
        print(f"{MARKER} exists: the test set has already been scored. Iterating on 2024-2025 is not allowed;")
        print("report the numbers in data/processed/test_evaluation.json instead. (--force to re-run the identical script.)")
        sys.exit(1)

    df = pd.read_parquet(nv.PROCESSED_DIR / "features.parquet")
    market = pd.read_parquet(nv.PROCESSED_DIR / "market.parquet").set_index("game_id")
    train = df[df.season.isin(nv.TRAIN_SEASONS)].copy()
    test = df[df.season.isin(nv.TEST_SEASONS)].copy()
    test = test[test.home_score.notna()].copy()
    m = market.loc[test.game_id]

    # ---- win model -------------------------------------------------------------
    wm = WinModel.load(WIN_MODEL_PATH, df=train)
    spec = json.load(open(WIN_MODEL_PATH))
    p_model = wm.predict_proba(test)
    p_raw = wm.predict_proba(test, calibrated=False)
    elo = RidgeLogit(1.0).fit(train.loc[train.home_win.notna(), ["elo0_diff"]].to_numpy(float),
                              train.loc[train.home_win.notna(), "home_win"].to_numpy(int))
    p_elo = elo.predict_proba(test[["elo0_diff"]].to_numpy(float))
    p_mkt, n_spread_fallback = market_probs(m, wm.sigma)
    test["p_model"], test["p_raw"], test["p_elo"], test["p_mkt"] = p_model, p_raw, p_elo, p_mkt

    ties = test.home_win.isna().sum()
    t = test[test.home_win.notna()].copy()
    y = t.home_win.to_numpy(int)
    print("=" * 90)
    print("  ONE-TIME TEST EVALUATION — 2024 + 2025 seasons (regular season + playoffs)")
    print("=" * 90)
    print(f"test games: {len(test)}  (ties excluded from win metrics: {ties});  model: {len(spec['features'])} features, "
          f"C={spec['C']}, blend={spec['blend']}, sigma={spec['sigma']:.2f}, calibration={spec.get('calibration_chosen')}")
    print(f"market: de-vigged closing moneyline; spread fallback used for {n_spread_fallback} games")

    results = {"n_test": int(len(test)), "ties_excluded": int(ties), "spread_fallback_games": n_spread_fallback,
               "model_spec": {k: spec[k] for k in ("features", "C", "blend", "sigma", "calibration_chosen")}}
    preds = {"model": t.p_model.to_numpy(), "model_raw": t.p_raw.to_numpy(), "elo": t.p_elo.to_numpy(), "market": t.p_mkt.to_numpy()}
    results["win_all"] = block(y, preds, "WIN MODEL — all test games")
    results["reliability"] = {k: reliability_table(y, preds[k]) for k in ("model", "market")}
    print("\nReliability (model | market):")
    for a, b in zip(results["reliability"]["model"], results["reliability"]["market"]):
        if a["n"] or b["n"]:
            print(f"  {a['bin']:<9} model n={a['n']:<4} pred={a['mean_pred']:.3f} obs={a['frac_pos']:.3f}   |  market n={b['n']:<4} pred={b['mean_pred']:.3f} obs={b['frac_pos']:.3f}")

    # agreement + bootstrap gaps
    agree = float(np.mean((t.p_model > 0.5) == (t.p_mkt > 0.5)))
    print(f"\nstraight-up favourite agreement, model vs market: {agree:.3f}")
    gaps = {}
    for other in ("market", "elo"):
        for metric, fn in (("log_loss", log_loss), ("brier", brier)):
            g = bootstrap_gap(y, preds["model"], preds[other], metric=fn)
            gaps[f"model_minus_{other}_{metric}"] = g
            print(f"  model - {other} {metric}: {g['gap']:+.4f}  95% CI [{g['ci_lo']:+.4f}, {g['ci_hi']:+.4f}]"
                  + ("  (within noise)" if g["within_noise"] else ""))
    results["agreement"] = agree; results["bootstrap_gaps"] = gaps

    # breakdowns
    results["breakdowns"] = {}
    t["qb_change"] = qb_change_flags(t.game_id).to_numpy()
    inj_thresh = float(np.quantile(np.abs(train.inj_total_diff), 0.9))
    t["major_injury"] = np.abs(t.inj_total_diff) >= inj_thresh
    segs = {
        "weeks_1_4": (t.week <= 4) & (t.game_type == "REG"),
        "weeks_5_18": (t.week >= 5) & (t.game_type == "REG"),
        "playoffs": t.game_type != "REG",
        "qb_change": t.qb_change, "no_qb_change": ~t.qb_change,
        "major_nonqb_injury": t.major_injury, "no_major_injury": ~t.major_injury,
        "season_2024": t.season == 2024, "season_2025": t.season == 2025,
    }
    for name, mask in segs.items():
        mask = mask.to_numpy()
        if mask.sum() < 10:
            continue
        results["breakdowns"][name] = block(y[mask], {k: v[mask] for k, v in preds.items() if k != "model_raw"}, f"segment: {name}")

    # ---- points model -----------------------------------------------------------
    print("\n" + "=" * 90); print("  POINTS MODEL — 2024 + 2025"); print("=" * 90)
    pspec = json.load(open(POINTS_MODEL_PATH)) if POINTS_MODEL_PATH.exists() else None
    avg = (train.home_score.mean() + train.away_score.mean()) / 2
    hadj = train.loc[train.neutral == 0, "margin"].mean() / 2
    base_home = avg + hadj * (1 - test.neutral); base_away = avg - hadj * (1 - test.neutral)
    mk_margin = m.spread_line.to_numpy(float); mk_total = m.total_line.to_numpy(float)
    mk_home = mk_total / 2 + mk_margin / 2; mk_away = mk_total / 2 - mk_margin / 2
    rowsP = {"baseline": (base_home.to_numpy(), base_away.to_numpy()), "market": (mk_home, mk_away)}
    if pspec:
        pm = PointsModel(pspec["features"], alpha=pspec["alpha"]).fit(train)
        pp = pm.predict(test)
        rowsP["model"] = (pp.pred_home.to_numpy(), pp.pred_away.to_numpy())
    # the shipped margin (from the win model's margin ridge) as well
    rowsP["win_model_margin"] = None
    results["points"] = {}
    print(f"{'':<18}{'home rmse':>10}{'home mae':>9}{'away rmse':>10}{'away mae':>9}{'margin rmse':>12}{'margin mae':>11}{'total rmse':>11}{'total mae':>10}")
    for name, pr in rowsP.items():
        if pr is None:
            mu = wm.predict_margin(test)
            r = {"margin_rmse": rmse(test.margin, mu), "margin_mae": mae(test.margin, mu)}
            print(f"{name:<18}{'':>10}{'':>9}{'':>10}{'':>9}{r['margin_rmse']:>12.3f}{r['margin_mae']:>11.3f}")
        else:
            h, a = pr
            r = {"home_rmse": rmse(test.home_score, h), "home_mae": mae(test.home_score, h),
                 "away_rmse": rmse(test.away_score, a), "away_mae": mae(test.away_score, a),
                 "margin_rmse": rmse(test.margin, h - a), "margin_mae": mae(test.margin, h - a),
                 "total_rmse": rmse(test.total, h + a), "total_mae": mae(test.total, h + a)}
            print(f"{name:<18}{r['home_rmse']:>10.3f}{r['home_mae']:>9.3f}{r['away_rmse']:>10.3f}{r['away_mae']:>9.3f}"
                  f"{r['margin_rmse']:>12.3f}{r['margin_mae']:>11.3f}{r['total_rmse']:>11.3f}{r['total_mae']:>10.3f}")
        results["points"][name] = r
    if pspec:
        mu_pts = rowsP["model"][0] - rowsP["model"][1]
        coh = float(np.mean((t.p_model > 0.5) == (mu_pts[test.home_win.notna().to_numpy()] > 0)))
        print(f"\nfavourite agreement, shipped win prob vs points-model margin: {coh:.3f}")
        results["coherence_points_vs_win"] = coh
        d = np.abs(mk_margin - mu_pts)
        print(f"|model margin - closing spread|: mean {d.mean():.2f}, median {np.median(d):.2f}")

    with open(OUT, "w") as f:
        json.dump(results, f, indent=1, default=float)
    MARKER.write_text("scored once by evaluate_test.py\n")
    print(f"\nwrote {OUT} and {MARKER}")


if __name__ == "__main__":
    main()
