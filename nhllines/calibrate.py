"""
Probability calibration report (roadmap step 4).
================================================
Fits Platt and isotonic calibrators on a held-out season and scores them, plus
the raw uncalibrated probabilities, on a never-seen final season. Reports log
loss, Brier, ECE and a reliability table, then a gate-style verdict: adopt a
calibrator only if it beats the raw probabilities on BOTH log loss and Brier.

The model defaults to `elo` — the Elo + home-ice baseline the model gate
currently ships. Pass --model logreg to calibrate the 44-feature candidate
instead (useful for confirming that its overconfidence is what calibration is
meant to fix).

Usage:
    python calibrate.py                       # calibrate the shipped Elo model
    python calibrate.py --model logreg        # calibrate the 44-feature logistic
    python calibrate.py --bins 15
"""

import argparse
import warnings

import numpy as np

from src.models.calibration import (
    choose_calibration, evaluate_calibration, reliability_table,
)

# Under this environment's BLAS (numpy/Accelerate) a spurious "divide by zero
# encountered in matmul" RuntimeWarning fires during logistic fitting despite
# producing identical, correct results (see the same note in elo_baseline.py).
warnings.filterwarnings("ignore", message=".*matmul.*", category=RuntimeWarning)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", choices=["elo", "logreg", "xg"], default="elo",
                        help="Which model's probabilities to calibrate (default: elo)")
    parser.add_argument("--training-set", default="data/training_set.csv")
    parser.add_argument("--bins", type=int, default=10,
                        help="Reliability / ECE bin count (default: 10)")
    args = parser.parse_args()

    result = evaluate_calibration(
        model_name=args.model, csv_path=args.training_set, n_bins=args.bins)
    by_method = {r["method"]: r for r in result["results"]}

    print("=" * 78)
    print("  PROBABILITY CALIBRATION — held-out-season Platt / isotonic")
    print("=" * 78)
    model_label = {
        "elo": "Elo + home-ice logistic (the shipped baseline)",
        "logreg": "44-feature point-in-time logistic (candidate)",
        "xg": "44-feature drop-goalie logistic (shipped production model)",
    }[args.model]
    print(f"  Model:            {model_label}")
    print(f"  Train seasons:    {', '.join(result['train_seasons'])} "
          f"({result['n_train']} games)")
    print(f"  Fit calibrator:   {result['calib_season']} "
          f"({result['n_calib']} games, held out from training)")
    print(f"  Test / score:     {result['test_season']} "
          f"({result['n_test']} games, unseen by model AND calibrator)")
    print("-" * 78)
    print(f"{'Method':<16}{'Accuracy':>10}{'Log loss':>11}{'Brier':>9}{'ECE':>9}")
    print("-" * 78)
    for r in result["results"]:
        print(f"{r['method']:<16}{r['accuracy']:>10.3f}{r['log_loss']:>11.4f}"
              f"{r['brier']:>9.4f}{r['ece']:>9.4f}")
    print("-" * 78)

    best, chosen = choose_calibration(result)
    base = by_method["uncalibrated"]

    print()
    if best is None:
        print("VERDICT: keep RAW probabilities — neither Platt nor isotonic beats the")
        print("         uncalibrated model on both log loss and Brier out-of-sample.")
        print(f"         Raw: log loss {base['log_loss']:.4f}, Brier {base['brier']:.4f}, "
              f"ECE {base['ece']:.4f}.")
        print("         The model is already well enough calibrated on a fresh season;")
        print("         adding a layer here would only fit calibration-season noise.")
    else:
        print(f"VERDICT: adopt {best.upper()} calibration — it beats the raw probabilities")
        print(f"         on both log loss ({chosen['log_loss']:.4f} < {base['log_loss']:.4f}) "
              f"and Brier ({chosen['brier']:.4f} < {base['brier']:.4f}).")
        print(f"         ECE {base['ece']:.4f} -> {chosen['ece']:.4f}. This replaces the "
              "hand-tuned")
        print("         confidence constants for this model's probability output.")

    # Reliability detail: the shape of the miscalibration, not just the summary
    # number. Bin on the raw probability (calibrators are monotone maps of it)
    # and show mean raw pred, observed win rate, and where the chosen calibrator
    # moves each bin.
    print()
    print("Reliability (test season) — raw vs "
          f"{'chosen: ' + best if best else 'raw only'}")
    print("-" * 78)
    header = f"{'prob bin':<14}{'n':>6}{'raw pred':>11}{'observed':>11}"
    if best:
        header += f"{'cal pred':>11}"
    print(header)

    p_raw = result["p_test_raw"]
    y = result["y_test"]
    chosen_cal = chosen["calibrator"] if best else None
    p_cal = chosen_cal.predict(p_raw) if chosen_cal else None

    edges = np.linspace(0.0, 1.0, args.bins + 1)
    idx = np.clip(np.digitize(p_raw, edges[1:-1]), 0, args.bins - 1)
    for row in reliability_table(p_raw, y, args.bins):
        if not row["count"]:
            continue
        label = f"[{row['lo']:.2f},{row['hi']:.2f})"
        line = (f"{label:<14}{row['count']:>6}"
                f"{row['mean_pred']:>11.3f}{row['frac_pos']:>11.3f}")
        if p_cal is not None:
            line += f"{p_cal[idx == row['bin']].mean():>11.3f}"
        print(line)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
