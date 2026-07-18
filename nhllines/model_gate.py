"""
Model gate: point-in-time ML model vs. Elo + home-ice logistic baseline.
=========================================================================
The standard NHL benchmark is Elo + home-ice-advantage logistic regression
(5 parameters). Any richer model earns the right to ship only if it beats
that baseline out-of-sample on proper scoring rules — log loss and Brier
score — computed on a held-out season. Win rate on a bet sample is NOT
admissible evidence here (see README: a 35-bet sample already burned this
project once).

The gate is intentionally strict: the candidate must beat the baseline on
BOTH log loss and Brier, not just one. A model that wins log loss but loses
Brier (or vice versa) is a mixed signal on a single held-out season, not a
real improvement — call it a wash and keep the baseline.

Usage:
    python model_gate.py                  # data/training_set.csv, default seasons
    python model_gate.py --candidate gbm  # gate the gradient-boosting model instead
"""

import argparse
import csv
import warnings

import numpy as np
from scipy.special import gammaln
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression, PoissonRegressor
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss, mean_squared_error
from sklearn.preprocessing import StandardScaler

from src.data.historical_dataset import FEATURE_COLUMNS
from src.models.elo_baseline import evaluate as evaluate_elo

# Spurious "divide by zero encountered in matmul" RuntimeWarning under this
# environment's BLAS (numpy/Accelerate) during logistic/Poisson fitting,
# despite producing identical, correct results (see elo_baseline.py).
warnings.filterwarnings("ignore", message=".*matmul.*", category=RuntimeWarning)


def _load_rows(path: str) -> list:
    with open(path) as f:
        return list(csv.DictReader(f))


def _to_xy(rows: list, columns: list, label: str = "home_win"):
    X = np.array([[float(r[c]) for c in columns] for r in rows])
    y = np.array([int(r[label]) for r in rows])
    return X, y


def evaluate_candidate(rows: list, candidate: str, columns: list = None) -> dict:
    """Time-split eval of the point-in-time feature set: train on all seasons
    but the most recent, test on the most recent — same split as the Elo
    baseline and build_training_set.py's validate(), so results are comparable.

    `columns` defaults to the full 44-feature set; pass a subset to gate a
    pruned candidate (see run_ablation() / --ablation)."""
    columns = columns or FEATURE_COLUMNS
    seasons = sorted(set(r["season"] for r in rows))
    test_season = seasons[-1]
    train = [r for r in rows if r["season"] != test_season]
    test = [r for r in rows if r["season"] == test_season]

    X_train, y_train = _to_xy(train, columns)
    X_test, y_test = _to_xy(test, columns)

    if candidate == "logreg":
        scaler = StandardScaler().fit(X_train)
        model = LogisticRegression(max_iter=2000, C=0.1, solver="liblinear")
        model.fit(scaler.transform(X_train), y_train)
        probs = model.predict_proba(scaler.transform(X_test))[:, 1]
        name = f"Logistic regression ({len(columns)} features)"
    elif candidate == "gbm":
        model = HistGradientBoostingClassifier(
            max_iter=300, max_depth=4, learning_rate=0.05,
            l2_regularization=1.0, random_state=42,
        )
        model.fit(X_train, y_train)
        probs = model.predict_proba(X_test)[:, 1]
        name = f"Gradient boosting ({len(columns)} features)"
    else:
        raise ValueError(f"Unknown candidate: {candidate}")

    return {
        "name": name,
        "test_season": test_season,
        "n_train": len(train),
        "n_test": len(test),
        "accuracy": accuracy_score(y_test, probs > 0.5),
        "log_loss": log_loss(y_test, probs),
        "brier": brier_score_loss(y_test, probs),
    }


# --------------------------------------------------------------------------- #
# Roadmap step 6: grouped feature ablation                                    #
# --------------------------------------------------------------------------- #
# Each block is dropped from the 44-feature set, one at a time, and the
# resulting reduced logistic regression is gated against Elo exactly like any
# other candidate — held-out log loss / Brier only, never accuracy.
FEATURE_BLOCKS = {
    "goalie": [
        "home_goalie_starts", "home_goalie_sv_pct", "home_goalie_gaa", "home_goalie_recent_sv_pct",
        "away_goalie_starts", "away_goalie_sv_pct", "away_goalie_gaa", "away_goalie_recent_sv_pct",
        "goalie_sv_pct_diff", "goalie_recent_sv_pct_diff", "goalie_experience_diff",
    ],
    "form": [
        "home_form_win_pct", "home_form_gf", "home_form_ga",
        "away_form_win_pct", "away_form_gf", "away_form_ga", "form_diff",
    ],
    "streak_trend": ["home_streak", "home_trend", "away_streak", "away_trend"],
    "h2h": ["h2h_home_win_rate", "h2h_meetings"],
    "splits": ["home_home_win_pct", "away_road_win_pct"],
    "xg": [
        "home_xgf_per60", "home_xga_per60", "home_high_danger_xg_share",
        "home_xg_luck_for", "home_xg_luck_against",
        "away_xgf_per60", "away_xga_per60", "away_high_danger_xg_share",
        "away_xg_luck_for", "away_xg_luck_against", "xg_diff_rate_diff",
    ],
}


def run_ablation(training_set_csv: str = "data/training_set.csv", candidate: str = "logreg") -> dict:
    """Gate a logistic (or gbm) candidate with each feature block dropped in
    turn from the 44-feature set. Does not touch build_training_set.py or
    historical_dataset.py — the training-set builder and its feature set are
    unchanged; this only varies which columns are handed to the candidate
    model at gate time."""
    rows = _load_rows(training_set_csv)
    seasons = sorted(set(r["season"] for r in rows))
    elo = evaluate_elo(seasons, training_set_csv)
    baseline = {
        "name": "Elo + home-ice logistic (baseline, 5 params)",
        "test_season": elo["test_season"],
        "accuracy": elo["accuracy"],
        "log_loss": elo["log_loss"],
        "brier": elo["brier"],
    }

    variants = []
    for block_name, drop_cols in FEATURE_BLOCKS.items():
        columns = [c for c in FEATURE_COLUMNS if c not in drop_cols]
        cand = evaluate_candidate(rows, candidate, columns=columns)
        beats_log_loss = cand["log_loss"] < baseline["log_loss"]
        beats_brier = cand["brier"] < baseline["brier"]
        variants.append({
            "block_dropped": block_name,
            "n_dropped": len(drop_cols),
            **cand,
            "beats_log_loss": beats_log_loss,
            "beats_brier": beats_brier,
            "passed": beats_log_loss and beats_brier,
        })

    return {"baseline": baseline, "variants": variants}


def run_gate(training_set_csv: str = "data/training_set.csv", candidate: str = "logreg") -> dict:
    rows = _load_rows(training_set_csv)
    seasons = sorted(set(r["season"] for r in rows))

    cand = evaluate_candidate(rows, candidate)

    elo = evaluate_elo(seasons, training_set_csv)
    baseline = {
        "name": "Elo + home-ice logistic (baseline, 5 params)",
        "test_season": elo["test_season"],
        "n_train": elo["n_train"],
        "n_test": elo["n_test"],
        "accuracy": elo["accuracy"],
        "log_loss": elo["log_loss"],
        "brier": elo["brier"],
    }

    beats_log_loss = cand["log_loss"] < baseline["log_loss"]
    beats_brier = cand["brier"] < baseline["brier"]
    passed = beats_log_loss and beats_brier

    return {
        "candidate": cand,
        "baseline": baseline,
        "beats_log_loss": beats_log_loss,
        "beats_brier": beats_brier,
        "passed": passed,
    }


# --------------------------------------------------------------------------- #
# Totals gate: point-in-time ML totals model vs. a league-average Poisson      #
# baseline.                                                                    #
# --------------------------------------------------------------------------- #
# The baseline for expected total goals is a Poisson distribution whose mean is
# simply the league-average total across the training seasons — no features at
# all. Any richer model earns the right to ship only if it beats that baseline
# out-of-sample on BOTH held-out RMSE of the expected total AND mean Poisson
# negative log-likelihood (not just one — same strict AND rule as the win gate).
def _poisson_nll(y_true, mu) -> float:
    """Mean Poisson negative log-likelihood: mu - y*log(mu) + log(y!)."""
    y = np.asarray(y_true, dtype=float)
    mu = np.clip(np.asarray(mu, dtype=float), 1e-6, None)
    return float(np.mean(mu - y * np.log(mu) + gammaln(y + 1.0)))


def evaluate_totals_baseline(rows: list, test_season: str) -> dict:
    """League-average Poisson: mean = average total_goals over every training
    season (all seasons but the held-out test season)."""
    train = [r for r in rows if r["season"] != test_season]
    test = [r for r in rows if r["season"] == test_season]
    y_train = np.array([float(r["total_goals"]) for r in train])
    y_test = np.array([float(r["total_goals"]) for r in test])

    mu = y_train.mean()
    preds = np.full(len(y_test), mu)

    return {
        "name": "League-average Poisson (baseline, 1 param)",
        "test_season": test_season,
        "n_train": len(train),
        "n_test": len(test),
        "mean_total": mu,
        "rmse": float(np.sqrt(mean_squared_error(y_test, preds))),
        "poisson_nll": _poisson_nll(y_test, preds),
    }


def evaluate_totals_candidate(rows: list, candidate: str, columns: list = None) -> dict:
    """Same time-split as the win-model gate: train on all seasons but the
    most recent, test on the most recent."""
    columns = columns or FEATURE_COLUMNS
    seasons = sorted(set(r["season"] for r in rows))
    test_season = seasons[-1]
    train = [r for r in rows if r["season"] != test_season]
    test = [r for r in rows if r["season"] == test_season]

    X_train = np.array([[float(r[c]) for c in columns] for r in train])
    y_train = np.array([float(r["total_goals"]) for r in train])
    X_test = np.array([[float(r[c]) for c in columns] for r in test])
    y_test = np.array([float(r["total_goals"]) for r in test])

    if candidate == "poisson":
        scaler = StandardScaler().fit(X_train)
        # newton-cholesky avoids the same spurious "divide by zero encountered
        # in matmul" RuntimeWarning that lbfgs triggers under this
        # environment's BLAS (see elo_baseline.py's identical note).
        model = PoissonRegressor(alpha=1.0, max_iter=1000, solver="newton-cholesky")
        model.fit(scaler.transform(X_train), y_train)
        preds = model.predict(scaler.transform(X_test))
        name = f"Poisson regression ({len(columns)} features)"
    elif candidate == "gbm":
        model = HistGradientBoostingRegressor(
            loss="poisson", max_iter=300, max_depth=4, learning_rate=0.05,
            l2_regularization=1.0, random_state=42,
        )
        model.fit(X_train, y_train)
        preds = model.predict(X_test)
        name = f"Gradient boosting, Poisson loss ({len(columns)} features)"
    else:
        raise ValueError(f"Unknown totals candidate: {candidate}")

    preds = np.clip(preds, 1e-6, None)
    return {
        "name": name,
        "test_season": test_season,
        "n_train": len(train),
        "n_test": len(test),
        "rmse": float(np.sqrt(mean_squared_error(y_test, preds))),
        "poisson_nll": _poisson_nll(y_test, preds),
    }


def run_totals_gate(training_set_csv: str = "data/training_set.csv",
                    candidate: str = "poisson") -> dict:
    rows = _load_rows(training_set_csv)
    seasons = sorted(set(r["season"] for r in rows))
    test_season = seasons[-1]

    baseline = evaluate_totals_baseline(rows, test_season)
    cand = evaluate_totals_candidate(rows, candidate)

    beats_rmse = cand["rmse"] < baseline["rmse"]
    beats_nll = cand["poisson_nll"] < baseline["poisson_nll"]
    passed = beats_rmse and beats_nll

    return {
        "candidate": cand,
        "baseline": baseline,
        "beats_rmse": beats_rmse,
        "beats_nll": beats_nll,
        "passed": passed,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--training-set", default="data/training_set.csv")
    parser.add_argument("--candidate", choices=["logreg", "gbm", "poisson"], default=None,
                        help="Which point-in-time model to gate. Win gate default: "
                             "logreg. Totals gate default: poisson.")
    parser.add_argument("--ablation", action="store_true",
                        help="Roadmap step 6: gate the candidate with each feature "
                             "block (goalie/form/streak_trend/h2h/splits) dropped in turn")
    parser.add_argument("--totals", action="store_true",
                        help="Gate a total-goals model (Poisson regression or "
                             "gradient boosting) against a league-average Poisson "
                             "baseline instead of the win-probability gate.")
    args = parser.parse_args()

    if args.totals:
        candidate = args.candidate or "poisson"
        result = run_totals_gate(args.training_set, candidate)
        cand, base = result["candidate"], result["baseline"]

        print("=" * 78)
        print("  TOTALS GATE — held-out RMSE / Poisson NLL vs league-average baseline")
        print("=" * 78)
        print(f"  Test season: {cand['test_season']}  "
              f"(train {cand['n_train']} games, test {cand['n_test']} games)")
        print("-" * 78)
        print(f"{'Model':<46}{'RMSE':>12}{'Poisson NLL':>18}")
        print("-" * 78)
        print(f"{base['name']:<46}{base['rmse']:>12.4f}{base['poisson_nll']:>18.4f}")
        print(f"{cand['name']:<46}{cand['rmse']:>12.4f}{cand['poisson_nll']:>18.4f}")
        print("-" * 78)

        print()
        if result["passed"]:
            print(f"GATE: PASS — {cand['name']} beats the baseline on BOTH")
            print(f"      RMSE ({cand['rmse']:.4f} < {base['rmse']:.4f}) and "
                  f"Poisson NLL ({cand['poisson_nll']:.4f} < {base['poisson_nll']:.4f}).")
            print("      Ship the candidate model.")
        else:
            reasons = []
            if not result["beats_rmse"]:
                reasons.append(f"RMSE {cand['rmse']:.4f} >= baseline {base['rmse']:.4f}")
            if not result["beats_nll"]:
                reasons.append(f"Poisson NLL {cand['poisson_nll']:.4f} >= "
                                f"baseline {base['poisson_nll']:.4f}")
            print(f"GATE: FAIL — {cand['name']} does not beat the baseline: "
                  + "; ".join(reasons) + ".")
            print("      Ship the league-average Poisson baseline instead.")

        return 0 if result["passed"] else 1

    args.candidate = args.candidate or "logreg"

    if args.ablation:
        result = run_ablation(args.training_set, args.candidate)
        base = result["baseline"]
        print("=" * 86)
        print("  GROUPED FEATURE ABLATION — held-out log loss / Brier vs Elo + home-ice baseline")
        print("=" * 86)
        print(f"{'Variant':<46}{'Accuracy':>10}{'Log loss':>11}{'Brier':>9}{'Beats Elo':>11}")
        print("-" * 86)
        print(f"{base['name']:<46}{base['accuracy']:>10.3f}{base['log_loss']:>11.4f}{base['brier']:>9.4f}{'':>11}")
        any_pass = False
        for v in result["variants"]:
            verdict = "PASS" if v["passed"] else "fail"
            any_pass = any_pass or v["passed"]
            label = f"drop {v['block_dropped']} ({v['name']})"
            print(f"{label:<46}{v['accuracy']:>10.3f}{v['log_loss']:>11.4f}{v['brier']:>9.4f}{verdict:>11}")
        print("-" * 86)
        print()
        if any_pass:
            winners = [v["block_dropped"] for v in result["variants"] if v["passed"]]
            print(f"GATE: at least one pruned variant beats Elo on BOTH log loss and Brier: "
                  + ", ".join(winners) + ".")
        else:
            print("GATE: no pruned variant beats the Elo + home-ice baseline on both log loss")
            print("      and Brier. Ship Elo, unchanged. (training-set builder untouched —")
            print("      this only varies which columns are handed to the candidate model.)")
        return 0 if any_pass else 1

    result = run_gate(args.training_set, args.candidate)
    cand, base = result["candidate"], result["baseline"]

    print("=" * 78)
    print("  MODEL GATE — held-out log loss / Brier vs Elo + home-ice baseline")
    print("=" * 78)
    print(f"  Test season: {cand['test_season']}  "
          f"(train {cand['n_train']} games, test {cand['n_test']} games)")
    print("-" * 78)
    print(f"{'Model':<46}{'Accuracy':>10}{'Log loss':>11}{'Brier':>9}")
    print("-" * 78)
    print(f"{base['name']:<46}{base['accuracy']:>10.3f}{base['log_loss']:>11.4f}{base['brier']:>9.4f}")
    print(f"{cand['name']:<46}{cand['accuracy']:>10.3f}{cand['log_loss']:>11.4f}{cand['brier']:>9.4f}")
    print("-" * 78)

    print()
    if result["passed"]:
        print(f"GATE: PASS — {cand['name']} beats the baseline on BOTH")
        print(f"      log loss ({cand['log_loss']:.4f} < {base['log_loss']:.4f}) and "
              f"Brier ({cand['brier']:.4f} < {base['brier']:.4f}).")
        print("      Ship the candidate model.")
    else:
        reasons = []
        if not result["beats_log_loss"]:
            reasons.append(f"log loss {cand['log_loss']:.4f} >= baseline {base['log_loss']:.4f}")
        if not result["beats_brier"]:
            reasons.append(f"Brier {cand['brier']:.4f} >= baseline {base['brier']:.4f}")
        print(f"GATE: FAIL — {cand['name']} does not beat the baseline: "
              + "; ".join(reasons) + ".")
        print("      Accuracy is not the metric that matters here — ship the Elo")
        print("      + home-ice baseline instead. Do not deploy the candidate.")

    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
