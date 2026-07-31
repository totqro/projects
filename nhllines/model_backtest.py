"""
Season backtest — the currently SHIPPED model against a real season, game by game.
====================================================================================
model_gate.py already proves the win model beats Elo out-of-sample, but only as
one aggregate number. This walks the same held-out season game by game: date,
matchup, the model's calibrated probability, what Elo would have said, and the
actual result — plus the same aggregate metrics model_gate.py reports, so the
two should agree.

The critical difference from every backtest*.py script already in this repo:
those all call src.models.ml_model / ml_model_streamlined — the quarantined,
leaky model the July 2026 rebuild replaced. Running them reports on a model
that hasn't been shipped in months. This script loads the ACTUAL persisted
artifacts (ml_models/xg_coefficients.json + xg_calibrator.json) via
xg_production.load_production_model() — the identical objects main.py loads —
and applies them to data/training_set.csv's point-in-time rows. No refitting,
no reimplementation of the model; it is exactly what's deployed.

That reuse comes with a constraint worth being explicit about: a season is
only a fair backtest of the CURRENT artifacts if it wasn't used to produce
them.
  - A season in xg_coefficients.json's trained_on_seasons was used to fit the
    logistic directly — testing on it is in-sample and this script refuses.
  - The held_out_calibration_season (currently 2025-26, model_gate.py's own
    held-out test season) is clean for the logistic's discrimination — it
    never saw those games — but the Platt calibrator WAS fit on exactly this
    season, so its calibration/ECE numbers here are not blind. That caveat is
    printed with the report, not hidden.
  - There is currently no season that is fully unseen by BOTH the logistic
    and the calibrator; 2025-26 (--gate-season) is the best available and is
    the default.

Usage:
    python model_backtest.py                       # the shipped model's held-out season
    python model_backtest.py --season 20252026
    python model_backtest.py --json data/model_backtest_20252026.json
"""

import argparse
import csv
import json
from pathlib import Path

from src.data.historical_dataset import XG_FEATURE_COLUMNS
from src.models import elo_production, xg_production
from src.models.elo_baseline import build_elo_rows
from src.models.calibration import reliability_table
from scorecard import totals_metrics, win_metrics

BASE = Path(__file__).resolve().parent
TRAINING_SET = BASE / "data" / "training_set.csv"
XG_COEFFICIENTS_PATH = BASE / "ml_models" / "xg_coefficients.json"


def _load_rows(csv_path: Path, season: str) -> list:
    with open(csv_path) as f:
        rows = [r for r in csv.DictReader(f) if r["season"] == season]
    rows.sort(key=lambda r: (r["date"], r["game_id"]))
    return rows


def model_provenance() -> dict:
    """trained_on_seasons / held_out_calibration_season straight from the
    persisted artifact, not assumed — if a refit changes the split, this
    script's validity check moves with it automatically."""
    return json.loads(XG_COEFFICIENTS_PATH.read_text())


def league_average_total(seasons: list, csv_path: Path = TRAINING_SET) -> float:
    """League-average total goals over `seasons` — the only totals baseline
    that has ever passed the totals gate (model_gate.py --totals). Callers
    pass seasons STRICTLY BEFORE the target season, so this is a forecast
    made without seeing the season being backtested."""
    totals = []
    with open(csv_path) as f:
        for row in csv.DictReader(f):
            if row["season"] in seasons:
                totals.append(float(row["total_goals"]))
    if not totals:
        raise ValueError(f"No training rows found for seasons {seasons}")
    return sum(totals) / len(totals)


def run_backtest(season: str, csv_path: Path = TRAINING_SET,
                 allow_in_sample: bool = False) -> dict:
    provenance = model_provenance()
    trained_on = set(provenance["trained_on_seasons"])
    calib_season = provenance["held_out_calibration_season"]

    if season in trained_on and not allow_in_sample:
        raise SystemExit(
            f"Season {season} was used to TRAIN the currently shipped xG "
            f"coefficients (trained_on_seasons={sorted(trained_on)}). "
            f"Backtesting the shipped model on it would report in-sample "
            f"performance — inflated, not a real test. Pass --allow-in-sample "
            f"if you understand this and want the (misleading) number anyway.")

    xg_coefs, xg_calibrator = xg_production.load_production_model()
    elo_coefs, elo_calibrator = elo_production.load_production_model()

    rows = _load_rows(csv_path, season)
    if not rows:
        raise SystemExit(f"No rows for season {season} in {csv_path}")

    # build_elo_rows() returns game_id as int (it casts internally); this
    # module's rows come straight off csv.DictReader, where every field
    # including game_id is a string. Key on str(...) on both sides, or the
    # join silently matches nothing and every Elo comparison goes missing.
    elo_by_gid = {str(r["game_id"]): r for r in build_elo_rows([season], str(csv_path))}

    all_seasons = sorted({r["season"] for r in csv.DictReader(open(csv_path))})
    prior_seasons = [s for s in all_seasons if s < season]
    totals_baseline_mu = (
        league_average_total(prior_seasons, csv_path) if prior_seasons else None)

    games = []
    for row in rows:
        xg_features = {c: float(row[c]) for c in XG_FEATURE_COLUMNS}
        p_xg, _ = xg_production.predict_calibrated(xg_coefs, xg_calibrator, xg_features)

        elo_row = elo_by_gid.get(str(row["game_id"]))
        p_elo = None
        if elo_row:
            p_elo, _ = elo_production.predict_calibrated(
                elo_coefs, elo_calibrator, elo_row["elo_diff"],
                elo_row["rest_diff"], elo_row["home_b2b"], elo_row["away_b2b"])

        games.append({
            "date": row["date"],
            "home_team": row["home_team"],
            "away_team": row["away_team"],
            "xg_home_win_prob": p_xg,
            "elo_home_win_prob": p_elo,
            "home_win": int(row["home_win"]),
            "total_goals": float(row["total_goals"]),
        })

    h2h = [g for g in games if g["elo_home_win_prob"] is not None]

    return {
        "season": season,
        "provenance": provenance,
        "calibration_season_caveat": season == calib_season,
        "n_games": len(games),
        "win": {
            "xg_all": win_metrics([g["xg_home_win_prob"] for g in games],
                                  [g["home_win"] for g in games]),
            "head_to_head": {
                "n": len(h2h),
                "xg": win_metrics([g["xg_home_win_prob"] for g in h2h],
                                  [g["home_win"] for g in h2h]),
                "elo": win_metrics([g["elo_home_win_prob"] for g in h2h],
                                   [g["home_win"] for g in h2h]),
            },
        },
        "totals": {
            "baseline_per_game": totals_baseline_mu,
            "baseline_seasons": prior_seasons,
            "vs_actual": (
                totals_metrics([totals_baseline_mu] * len(games),
                               [g["total_goals"] for g in games])
                if totals_baseline_mu is not None else {}),
        },
        "reliability": reliability_table(
            [g["xg_home_win_prob"] for g in games], [g["home_win"] for g in games]),
        "games": games,
    }


def _biggest_misses(games: list, n: int = 5) -> list:
    """Most confident-and-wrong calls: high |p - 0.5| in the wrong direction.
    This is the exact failure mode the July 2026 diagnosis flagged in the old
    model (confident bins going 2/13) — surfacing it here rather than only in
    an aggregate ECE number."""
    def wrongness(g):
        predicted_home = g["xg_home_win_prob"] > 0.5
        actual_home = bool(g["home_win"])
        if predicted_home == actual_home:
            return -1.0
        return abs(g["xg_home_win_prob"] - 0.5)
    ranked = sorted(games, key=wrongness, reverse=True)
    return [g for g in ranked[:n] if wrongness(g) > 0]


def print_report(card: dict) -> None:
    prov = card["provenance"]
    print("=" * 78)
    print(f"  SEASON BACKTEST — shipped xG model vs Elo baseline, {card['season']}")
    print("=" * 78)
    print(f"  Games: {card['n_games']}")
    print(f"  Model trained on: {', '.join(prov['trained_on_seasons'])}")
    print(f"  Calibrator fit on: {prov['held_out_calibration_season']}")
    if card["calibration_season_caveat"]:
        print("  ⚠️  This IS the calibrator's fitting season — win/loss discrimination")
        print("      below is a fair out-of-sample test, but the calibration/ECE")
        print("      numbers are not blind (the calibrator saw these exact games).")
    print("-" * 78)

    m = card["win"]["xg_all"]
    print(f"{'Model':<30}{'n':>6}{'Accuracy':>10}{'Log loss':>11}{'Brier':>9}{'ECE':>8}")
    print("-" * 78)
    print(f"{'Shipped xG model':<30}{m['n']:>6}{m['accuracy']:>10.3f}"
          f"{m['log_loss']:>11.4f}{m['brier']:>9.4f}{m['ece']:>8.4f}")

    h2h = card["win"]["head_to_head"]
    if h2h["n"]:
        hx, he = h2h["xg"], h2h["elo"]
        print(f"{'  vs Elo, same games — xG':<30}{hx['n']:>6}{hx['accuracy']:>10.3f}"
              f"{hx['log_loss']:>11.4f}{hx['brier']:>9.4f}{hx['ece']:>8.4f}")
        print(f"{'  vs Elo, same games — Elo':<30}{he['n']:>6}{he['accuracy']:>10.3f}"
              f"{he['log_loss']:>11.4f}{he['brier']:>9.4f}{he['ece']:>8.4f}")
        gap = hx["log_loss"] - he["log_loss"]
        verb = "beats" if gap < 0 else "trails"
        print(f"  xG {verb} Elo by {abs(gap):.4f} log loss on {h2h['n']} games.")

    t = card["totals"]
    if t.get("vs_actual"):
        v = t["vs_actual"]
        print("-" * 78)
        print(f"  TOTALS — league-average baseline ({', '.join(t['baseline_seasons'])}), "
              f"no model has ever beaten it")
        print(f"    Baseline: {t['baseline_per_game']:.2f} goals/game flat "
              f"-> RMSE {v['rmse']:.4f}, MAE {v['mae']:.3f}, Poisson NLL {v['poisson_nll']:.4f}")

    misses = _biggest_misses(card["games"])
    if misses:
        print("-" * 78)
        print("  Most confident wrong calls:")
        for g in misses:
            called = g["home_team"] if g["xg_home_win_prob"] > 0.5 else g["away_team"]
            actual = g["home_team"] if g["home_win"] else g["away_team"]
            print(f"    {g['date']}  {g['away_team']} @ {g['home_team']}  "
                  f"called {called} ({g['xg_home_win_prob']:.0%})  actual: {actual}")
    print("-" * 78)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--season", default=None,
                        help="Season to backtest, e.g. 20252026 (default: the "
                             "shipped model's own held-out calibration season)")
    parser.add_argument("--training-set", default=str(TRAINING_SET))
    parser.add_argument("--allow-in-sample", action="store_true",
                        help="Backtest a season the model was TRAINED on anyway "
                             "(inflated, not a real test — use only to see why)")
    parser.add_argument("--json", dest="json_path", default=None)
    args = parser.parse_args()

    season = args.season or model_provenance()["held_out_calibration_season"]
    card = run_backtest(season, Path(args.training_set), args.allow_in_sample)
    print_report(card)

    if args.json_path:
        out = Path(args.json_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(card, indent=2))
        print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
