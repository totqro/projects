#!/usr/bin/env python3
"""
MLB model gate: does anything beat Elo + home field out of sample?
==================================================================
Win model: the pitcher-aware logistic must beat the 2-parameter Elo + home
field logistic on BOTH log loss and Brier on the held-out season. Accuracy and
the always-home rate are printed for context, never used to decide.

Totals: the negative-binomial GLM must beat a league-average baseline on BOTH
RMSE and NLL on the held-out season.

Leave-one-season-out results are printed alongside, so a pass that only holds
in one season is visible.

Usage:
    python model_gate.py                 # both gates, from mlbdata/training_set.csv
    python model_gate.py --win           # win gate only
    python model_gate.py --totals        # totals gate only
Exit code 0 when every gate run passes, 1 otherwise.
"""

import argparse
import json
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
warnings.filterwarnings("ignore", category=RuntimeWarning)

from src.data.historical_dataset import load_csv
from src.models import totals_model, win_model

TRAINING_SET = Path(__file__).resolve().parent / "mlbdata" / "training_set.csv"


def print_win_gate(g: dict) -> None:
    print("=" * 84)
    print("  WIN GATE — held-out log loss / Brier vs Elo + home field")
    print("=" * 84)
    print(f"{'Season':<8}{'Model':<34}{'Acc':>8}{'Log loss':>11}{'Brier':>9}{'ECE':>8}")
    print("-" * 84)
    for i, r in enumerate([g["primary"]] + g["loso"]):
        if i == 1:
            print("-" * 84)
            print("  Leave-one-season-out (train on every other season):")
        tag = f"{r['test_season']}" + (" *" if i == 0 else "")
        for key in ("always_home", "elo", "pitcher"):
            label = {"always_home": "Always home (constant)",
                     "elo": "Elo + home field",
                     "pitcher": "Pitcher model"}[key]
            m = r[key]
            print(f"{tag:<8}{label:<34}{m['accuracy']:>8.3f}{m['log_loss']:>11.4f}"
                  f"{m['brier']:>9.4f}{m['ece']:>8.4f}")
            tag = ""
        print(f"{'':<8}{'-> pitcher beats Elo: ' + ('PASS' if r['pitcher_beats_elo'] else 'fail')}")
    print("-" * 84)
    print("  * primary split: trained only on seasons before the test season")
    print(f"  Pitcher model beats Elo in {g['loso_pitcher_wins']} of {len(g['loso'])} held-out seasons.")
    print(f"  GATE: {'PASS — ship the pitcher model' if g['passed'] else 'FAIL — ship Elo + home field'}")


def print_totals_gate(g: dict) -> None:
    print("=" * 84)
    print("  TOTALS GATE — held-out RMSE / NB log-likelihood vs league-average baseline")
    print("=" * 84)
    print(f"{'Season':<10}{'Base RMSE':>11}{'Base NLL':>10}{'GLM RMSE':>11}{'GLM NLL':>10}{'Verdict':>10}")
    print("-" * 84)
    for i, r in enumerate([g["primary"]] + g["loso"]):
        b, m = r["baseline"], r["glm"]
        tag = f"{r['test_season']}" + (" *" if i == 0 else "")
        print(f"{tag:<10}{b['rmse']:>11.4f}{b['nb_nll']:>10.4f}{m['rmse']:>11.4f}"
              f"{m['nb_nll']:>10.4f}{'PASS' if r['glm_beats_baseline'] else 'fail':>10}")
    print("-" * 84)
    print(f"  GLM beats the baseline in {g['loso_glm_wins']} of {len(g['loso'])} held-out seasons.")
    print(f"  GATE: {'PASS — ship the GLM' if g['passed'] else 'FAIL — ship the league average'}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--training-set", default=str(TRAINING_SET))
    ap.add_argument("--win", action="store_true")
    ap.add_argument("--totals", action="store_true")
    ap.add_argument("--json", dest="json_path")
    args = ap.parse_args()
    both = not args.win and not args.totals

    rows = load_csv(args.training_set)
    out, ok = {}, True
    if args.win or both:
        g = win_model.run_gate(rows)
        print_win_gate(g)
        out["win"] = g
        ok = ok and g["passed"]
        cal = win_model.run_calibration_check(rows, g["winner"])
        if "raw" in cal:
            print(f"\n  Calibration ({cal['calibration_season']} fit, {cal['test_season']} scored): "
                  f"raw ll {cal['raw']['log_loss']:.4f} / Brier {cal['raw']['brier']:.4f}  vs  "
                  f"Platt ll {cal['platt']['log_loss']:.4f} / Brier {cal['platt']['brier']:.4f}"
                  f"  -> {'adopt Platt' if cal['adopted'] else 'keep raw probabilities'}")
        out["calibration"] = cal
        print()
    if args.totals or both:
        g = totals_model.run_gate(rows)
        print_totals_gate(g)
        out["totals"] = g
        ok = ok and g["passed"]

    if args.json_path:
        Path(args.json_path).write_text(json.dumps(out, indent=2, default=str))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
