"""
Build the point-in-time multi-season training set.

Usage:
    python build_training_set.py                     # 4 seasons -> data/training_set.csv
    python build_training_set.py --seasons 20232024 20242025
    python build_training_set.py --validate          # also run time-split sanity check

The validation holds out the most recent season, trains simple models on the
earlier seasons, and reports accuracy / log loss / Brier vs an always-home
baseline. This is a sanity check that the dataset carries real signal —
NOT a betting backtest (no odds involved).
"""

import argparse

from src.data.historical_dataset import (
    build_training_set, FEATURE_COLUMNS, seasons_through_current,
)

# Rolling: picks up a new season automatically once it starts (July 1).
DEFAULT_SEASONS = seasons_through_current("20222023")


def validate(rows: list, out_path: str = "data/training_set.csv"):
    """Time-split sanity check: train on all seasons but the last, test on the last."""
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import accuracy_score, log_loss, brier_score_loss

    seasons = sorted(set(r["season"] for r in rows))
    if len(seasons) < 2:
        print("Need at least 2 seasons to validate")
        return
    test_season = seasons[-1]

    def to_xy(subset):
        X = np.array([[float(r[c]) for c in FEATURE_COLUMNS] for r in subset])
        y = np.array([r["home_win"] for r in subset])
        return X, y

    train_rows = [r for r in rows if r["season"] != test_season]
    test_rows = [r for r in rows if r["season"] == test_season]
    X_train, y_train = to_xy(train_rows)
    X_test, y_test = to_xy(test_rows)

    print(f"\nValidation: train on {seasons[:-1]} ({len(train_rows)} games), "
          f"test on {test_season} ({len(test_rows)} games)")
    print("-" * 72)
    print(f"{'Model':<28} {'Accuracy':>9} {'Log loss':>9} {'Brier':>8}")
    print("-" * 72)

    # Baseline: constant home-win probability from training data
    p_home = y_train.mean()
    const_probs = np.full(len(y_test), p_home)
    print(f"{'Always-home baseline':<28} "
          f"{accuracy_score(y_test, np.ones(len(y_test))):>9.3f} "
          f"{log_loss(y_test, const_probs):>9.4f} "
          f"{brier_score_loss(y_test, const_probs):>8.4f}")

    scaler = StandardScaler().fit(X_train)
    lr = LogisticRegression(max_iter=2000, C=0.1)
    lr.fit(scaler.transform(X_train), y_train)
    lr_probs = lr.predict_proba(scaler.transform(X_test))[:, 1]
    print(f"{'Logistic regression':<28} "
          f"{accuracy_score(y_test, lr_probs > 0.5):>9.3f} "
          f"{log_loss(y_test, lr_probs):>9.4f} "
          f"{brier_score_loss(y_test, lr_probs):>8.4f}")

    gbm = HistGradientBoostingClassifier(
        max_iter=300, max_depth=4, learning_rate=0.05,
        l2_regularization=1.0, random_state=42,
    )
    gbm.fit(X_train, y_train)
    gbm_probs = gbm.predict_proba(X_test)[:, 1]
    print(f"{'Gradient boosting':<28} "
          f"{accuracy_score(y_test, gbm_probs > 0.5):>9.3f} "
          f"{log_loss(y_test, gbm_probs):>9.4f} "
          f"{brier_score_loss(y_test, gbm_probs):>8.4f}")

    # The gate: Elo + home-ice logistic regression (5 params) is the dumb
    # baseline every model here has to beat out-of-sample. Same test season,
    # same games — no cherry-picking.
    from src.models.elo_baseline import evaluate as evaluate_elo
    elo_result = evaluate_elo(seasons, training_set_csv=out_path)
    print(f"{'Elo + home-ice (5-param)':<28} "
          f"{elo_result['accuracy']:>9.3f} "
          f"{elo_result['log_loss']:>9.4f} "
          f"{elo_result['brier']:>8.4f}")

    print("-" * 72)
    print("Reference points: NHL home teams win ~53-55%; the market closing")
    print("line is ~59-60% accurate with log loss ~0.66. A model between the")
    print("baseline and the market is learning real signal without leakage.")

    # Top logistic coefficients as a leakage smell test — sane features
    # (win% diff, form, rest) should dominate, not oddities.
    coefs = sorted(zip(FEATURE_COLUMNS, lr.coef_[0]),
                   key=lambda t: abs(t[1]), reverse=True)
    print("\nTop 10 logistic coefficients (|weight|):")
    for name, w in coefs[:10]:
        print(f"  {name:<24} {w:+.3f}")

    # Gate verdict: does anything beat Elo on BOTH log loss and Brier?
    # Win rate / accuracy is explicitly not the criterion — it's noisy and
    # rewards overconfident models on a single held-out season.
    candidates = {
        "Logistic regression": (log_loss(y_test, lr_probs), brier_score_loss(y_test, lr_probs)),
        "Gradient boosting": (log_loss(y_test, gbm_probs), brier_score_loss(y_test, gbm_probs)),
    }
    elo_ll, elo_brier = elo_result["log_loss"], elo_result["brier"]
    winners = [name for name, (ll, br) in candidates.items()
               if ll < elo_ll and br < elo_brier]

    print("\n" + "=" * 72)
    print("GATE: does the ML model beat the Elo baseline out-of-sample?")
    print("=" * 72)
    for name, (ll, br) in candidates.items():
        verdict = "BEATS Elo" if name in winners else "does NOT beat Elo"
        print(f"  {name:<24} log loss {ll:.4f} vs {elo_ll:.4f}  |  "
              f"Brier {br:.4f} vs {elo_brier:.4f}  ->  {verdict}")
    if winners:
        best = min(winners, key=lambda n: candidates[n][0])
        print(f"\n  PASS — {best} beats the Elo baseline on both metrics. Ship it.")
    else:
        print("\n  FAIL — no ML model beats the Elo baseline out-of-sample.")
        print("  Ship the Elo + home-ice logistic regression baseline instead.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seasons", nargs="+", default=DEFAULT_SEASONS,
                        help="Seasons like 20242025 (default: last 4)")
    parser.add_argument("--min-gp", type=int, default=5,
                        help="Skip games where either team has fewer season GP (default 5)")
    parser.add_argument("--out", default="data/training_set.csv")
    parser.add_argument("--validate", action="store_true",
                        help="Run time-split sanity check after building")
    parser.add_argument("--no-goalies", action="store_true",
                        help="Skip fetching actual starting goalies (faster, "
                             "drops goalie features to league-average priors)")
    args = parser.parse_args()

    print("=" * 72)
    print("  POINT-IN-TIME TRAINING SET BUILDER")
    print("=" * 72)
    rows = build_training_set(args.seasons, min_gp=args.min_gp, out_path=args.out,
                              with_goalies=not args.no_goalies)

    if args.validate and rows:
        validate(rows, out_path=args.out)

    if rows:
        print("\n" + "=" * 72)
        print("  REFITTING PRODUCTION CALIBRATOR (Elo + home-ice, Platt)")
        print("=" * 72)
        from src.models.elo_production import fit_and_persist, CALIBRATOR_PATH, COEFFICIENTS_PATH
        summary = fit_and_persist(args.seasons, csv_path=args.out)
        print(f"  Trained on: {', '.join(summary['seasons'])}")
        print(f"  Calibrator: {summary['calibrator_method']} "
              f"(fit on held-out {summary['held_out_calibration_season']})")
        print(f"  Wrote {CALIBRATOR_PATH}")
        print(f"  Wrote {COEFFICIENTS_PATH}")


if __name__ == "__main__":
    main()
