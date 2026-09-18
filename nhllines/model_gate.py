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

from src.data.historical_dataset import FEATURE_COLUMNS, GOALIE_FEATURE_COLUMNS
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


def evaluate_candidate(rows: list, candidate: str, columns: list = None,
                       test_season: str = None) -> dict:
    """Time-split eval of the point-in-time feature set: train on all seasons
    but the held-out one, test on it — same split as the Elo baseline and
    build_training_set.py's validate(), so results are comparable.

    `columns` defaults to the full 44-feature set; pass a subset to gate a
    pruned candidate (see run_ablation() / --ablation). `test_season` defaults
    to the chronologically last season in `rows`, matching every existing
    caller; pass an explicit one to hold out a DIFFERENT season instead (see
    run_loso() / --loso, which holds out every available season in turn)."""
    columns = columns or FEATURE_COLUMNS
    seasons = sorted(set(r["season"] for r in rows))
    test_season = test_season or seasons[-1]
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
    "goalie": GOALIE_FEATURE_COLUMNS,
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
# Leave-one-season-out: does xG beat Elo in EVERY available season, or did    #
# the single held-out-season result the model shipped on get lucky?          #
# --------------------------------------------------------------------------- #
# data/training_set.csv only covers 2022-23 onward. MoneyPuck's public shots
# dataset (the xG source) goes back to 2018-19 — four more seasons than the
# production pipeline currently uses. Fetched fresh here, in memory, for this
# test only: never written to training_set.csv, never touches
# build_training_set.py's season list. historical_dataset.MONEYPUCK_SEASONS
# is patched for the duration of each fetch and restored immediately after —
# that module-level check is what makes build_point_in_time_rows() compute
# real xG features instead of silently falling back to neutral defaults for a
# season it doesn't recognize.
EXTRA_LOSO_SEASONS = ["20182019", "20192020", "20202021", "20212022"]

# 2019-20: paused in March 2020 by COVID, finished via bubble playoffs — the
# REGULAR season itself is simply truncated (~68-71 games/team instead of 82),
# not restructured, so it's usable as-is; there's just less of it.
# 2020-21: the real anomaly — a 56-game season with an all-Canadian "North"
# division (closed borders), unlike any other season in this set. Included
# for completeness but called out separately in the report, not blended in
# silently.
ANOMALOUS_LOSO_SEASONS = {"20192020", "20202021"}


def _fetch_extra_season_rows(season: str, verbose: bool = True) -> tuple:
    """Point-in-time rows for a season NOT in training_set.csv, matching its
    exact column schema (build_point_in_time_rows() emits the same field
    names historical_dataset.write_csv() does). Returns (rows, games) — the
    raw games list is returned too so the Elo step below can reuse it instead
    of re-fetching the same schedule a second time."""
    import src.data.historical_dataset as hd
    from src.data.moneypuck_data import load_moneypuck_xg

    original = hd.MONEYPUCK_SEASONS
    hd.MONEYPUCK_SEASONS = original | frozenset([season])
    try:
        games = hd.fetch_season_games_full(season, verbose=verbose)
        xg_data = load_moneypuck_xg([season])
        missing = [g for g in games if g["id"] not in xg_data]
        if missing:
            if verbose:
                print(f"  {season}: {len(missing)} game(s) missing MoneyPuck xG "
                      f"coverage, excluded (not silently dropped): "
                      + ", ".join(f"{g['date']} {g['away_team']}@{g['home_team']}"
                                  for g in missing))
            games = [g for g in games if g["id"] in xg_data]
        rows = hd.build_point_in_time_rows(games, starters=None, xg_data=xg_data)
        return [r for r in rows if r["season"] == season], games
    finally:
        hd.MONEYPUCK_SEASONS = original


def _loso_rows(training_set_csv: str, extra_seasons: list, verbose: bool = True) -> tuple:
    """training_set.csv's rows plus every requested extra season, fetched
    fresh in memory. Returns (rows, extra_games) — extra_games feeds the Elo
    computation below so it isn't fetched twice."""
    rows = _load_rows(training_set_csv)
    extra_games = []
    for season in extra_seasons:
        if verbose:
            print(f"Fetching {season} (not in {training_set_csv})...")
        extra_rows, games = _fetch_extra_season_rows(season, verbose=verbose)
        rows.extend(extra_rows)
        extra_games.extend(games)
        if verbose:
            print(f"  {len(extra_rows)} point-in-time rows")
    return rows, extra_games


def _gather_elo_games(rows: list, extra_games: list, verbose: bool = True) -> list:
    """Every game across every season present in `rows`, fetched once. Reused
    by _attach_elo() (single default reversion) and the --tune-elo-reversion
    sweep (many reversion values against the SAME game set, so it's fetched
    once here rather than once per candidate value)."""
    from src.data.historical_dataset import fetch_season_games_full

    seasons_needed = sorted(set(r["season"] for r in rows))
    fetched_seasons = {g["season"] for g in extra_games}
    all_games = list(extra_games)
    for season in seasons_needed:
        if season not in fetched_seasons:
            if verbose:
                print(f"Fetching {season} game results for Elo...")
            all_games.extend(fetch_season_games_full(season, verbose=False))
    return all_games


def _attach_elo_from_games(rows: list, all_games: list, season_reversion: float = None) -> list:
    """Pregame Elo for every row, computed over the FULL chronological game
    sequence across every season present. This is safe to do once regardless
    of which season a later step holds out: compute_pregame_elo() only ever
    uses games strictly before the game in question, so the rating itself
    can't leak a held-out season's outcome into an earlier game. Only the
    elo_diff -> P(win) LOGISTIC needs a clean train/test split per season,
    which run_loso() does with the ratings this function already computed."""
    from src.models.elo_baseline import compute_pregame_elo

    pregame_elo = compute_pregame_elo(all_games, season_reversion)
    out = []
    for r in rows:
        gid = int(r["game_id"])
        if gid not in pregame_elo:
            continue
        elo_home, elo_away = pregame_elo[gid]
        out.append({
            "game_id": gid,
            "season": r["season"],
            "elo_diff": elo_home - elo_away,
            "rest_diff": float(r["rest_diff"]),
            "home_b2b": float(r["home_b2b"]),
            "away_b2b": float(r["away_b2b"]),
            "home_win": int(r["home_win"]),
        })
    return out


def _evaluate_elo_held_out(elo_rows: list, test_season: str) -> dict:
    """Elo + home-ice logistic, held out on `test_season` — same fit as
    elo_baseline.evaluate(), generalized to hold out an arbitrary season
    rather than always the chronologically last one."""
    train = [r for r in elo_rows if r["season"] != test_season]
    test = [r for r in elo_rows if r["season"] == test_season]

    X_train = np.array([[r[c] for c in ["elo_diff", "rest_diff", "home_b2b", "away_b2b"]]
                        for r in train])
    y_train = np.array([r["home_win"] for r in train])
    X_test = np.array([[r[c] for c in ["elo_diff", "rest_diff", "home_b2b", "away_b2b"]]
                       for r in test])
    y_test = np.array([r["home_win"] for r in test])

    scaler = StandardScaler().fit(X_train)
    model = LogisticRegression(max_iter=2000, solver="liblinear")
    model.fit(scaler.transform(X_train), y_train)
    probs = model.predict_proba(scaler.transform(X_test))[:, 1]

    return {
        "test_season": test_season,
        "n_train": len(train),
        "n_test": len(test),
        "accuracy": accuracy_score(y_test, probs > 0.5),
        "log_loss": log_loss(y_test, probs),
        "brier": brier_score_loss(y_test, probs),
    }


def run_loso(training_set_csv: str = "data/training_set.csv", candidate: str = "logreg",
            extra_seasons: list = None, verbose: bool = True) -> dict:
    """Hold out EVERY available season in turn — not just the one the shipped
    model happens to be gated on — training the candidate and Elo fresh each
    time on every other season. Answers the question a single held-out split
    can't: does the candidate beat Elo repeatably, or did it win once by the
    variance of a single test season?"""
    extra_seasons = EXTRA_LOSO_SEASONS if extra_seasons is None else extra_seasons
    rows, extra_games = _loso_rows(training_set_csv, extra_seasons, verbose)
    seasons = sorted(set(r["season"] for r in rows))

    if verbose:
        print(f"\nComputing Elo across all {len(seasons)} seasons...")
    all_elo_games = _gather_elo_games(rows, extra_games, verbose)
    elo_rows = _attach_elo_from_games(rows, all_elo_games)

    per_season = []
    for test_season in seasons:
        cand = evaluate_candidate(rows, candidate, test_season=test_season)
        elo = _evaluate_elo_held_out(elo_rows, test_season)
        per_season.append({
            "season": test_season,
            "anomalous": test_season in ANOMALOUS_LOSO_SEASONS,
            "n_test": cand["n_test"],
            "candidate_log_loss": cand["log_loss"],
            "candidate_brier": cand["brier"],
            "candidate_accuracy": cand["accuracy"],
            "elo_log_loss": elo["log_loss"],
            "elo_brier": elo["brier"],
            "elo_accuracy": elo["accuracy"],
            "beats_elo_log_loss": cand["log_loss"] < elo["log_loss"],
            "beats_elo_brier": cand["brier"] < elo["brier"],
        })

    clean = [s for s in per_season if not s["anomalous"]]
    n_beats_both = sum(1 for s in clean if s["beats_elo_log_loss"] and s["beats_elo_brier"])
    return {
        "candidate": candidate,
        "seasons_tested": seasons,
        "per_season": per_season,
        "summary": {
            "n_seasons_clean": len(clean),
            "n_beats_elo_both_metrics": n_beats_both,
            "mean_log_loss_gap": (sum(s["elo_log_loss"] - s["candidate_log_loss"] for s in clean)
                                 / len(clean)) if clean else float("nan"),
        },
    }


# --------------------------------------------------------------------------- #
# Elo season-reversion sweep: is 1/3 actually a good number, or just a guess   #
# nobody tested?                                                              #
# --------------------------------------------------------------------------- #
# elo_baseline.SEASON_REVERSION regresses 1/3 of a team's rating back toward
# 1500 at every season boundary — a hand-picked constant, never validated
# against real held-out seasons the way every other number in this project
# is. This sweeps candidate values and scores each one with the SAME
# leave-one-season-out discipline as run_loso(), so "should it be bigger"
# gets a real, checkable answer instead of a guess prompted by one team's
# surprising rating (see docs/ or ask about the 2025-26 SJS case).
REVERSION_CANDIDATES = [0.0, 0.15, 0.25, 1.0 / 3.0, 0.5, 2.0 / 3.0, 1.0]


def run_reversion_sweep(training_set_csv: str = "data/training_set.csv",
                        extra_seasons: list = None, candidates: list = None,
                        verbose: bool = True) -> dict:
    """For each candidate season-reversion fraction, hold out every available
    season in turn and score Elo's own held-out log loss / Brier — no xG
    model involved, this only tunes Elo against itself. The games are fetched
    ONCE and reused across every candidate value; only the (cheap) Elo walk
    and the small 4-feature logistic are redone per candidate."""
    extra_seasons = EXTRA_LOSO_SEASONS if extra_seasons is None else extra_seasons
    candidates = REVERSION_CANDIDATES if candidates is None else candidates

    rows, extra_games = _loso_rows(training_set_csv, extra_seasons, verbose)
    seasons = sorted(set(r["season"] for r in rows))
    clean_seasons = [s for s in seasons if s not in ANOMALOUS_LOSO_SEASONS]

    if verbose:
        print(f"\nFetching games once for the sweep ({len(seasons)} seasons)...")
    all_games = _gather_elo_games(rows, extra_games, verbose)

    results = []
    for reversion in candidates:
        elo_rows = _attach_elo_from_games(rows, all_games, season_reversion=reversion)
        per_season = []
        for test_season in clean_seasons:
            elo = _evaluate_elo_held_out(elo_rows, test_season)
            per_season.append({"season": test_season, "log_loss": elo["log_loss"],
                              "brier": elo["brier"], "n_test": elo["n_test"]})
        mean_log_loss = sum(s["log_loss"] for s in per_season) / len(per_season)
        mean_brier = sum(s["brier"] for s in per_season) / len(per_season)
        results.append({
            "reversion": reversion,
            "per_season": per_season,
            "mean_log_loss": mean_log_loss,
            "mean_brier": mean_brier,
        })
        if verbose:
            print(f"  reversion={reversion:.3f}  mean log loss={mean_log_loss:.4f}  "
                  f"mean Brier={mean_brier:.4f}")

    best = min(results, key=lambda r: r["mean_log_loss"])
    current = next((r for r in results if abs(r["reversion"] - 1.0 / 3.0) < 1e-9), None)
    return {
        "clean_seasons": clean_seasons,
        "results": results,
        "best": best,
        "current_production_value": current,
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
    parser.add_argument("--loso", action="store_true",
                        help="Leave-one-season-out: hold out EVERY available season "
                             "in turn (not just the one split the shipped model is "
                             "gated on) and report whether the candidate beats Elo "
                             "in each one. Fetches 2018-19 through 2021-22 fresh "
                             "in memory (MoneyPuck xG coverage starts 2018-19); "
                             "training_set.csv and the production pipeline are "
                             "untouched. See --loso-seasons to change the extra set.")
    parser.add_argument("--loso-seasons", default=None,
                        help="Comma-separated extra seasons to fetch for --loso "
                             "(default: 20182019,20192020,20202021,20212022)")
    parser.add_argument("--tune-elo-reversion", action="store_true",
                        help="Sweep Elo's season-boundary reversion fraction "
                             "(currently a hardcoded 1/3, never validated) "
                             "against every held-out season, and report which "
                             "value actually predicts best.")
    args = parser.parse_args()

    if args.tune_elo_reversion:
        extra = args.loso_seasons.split(",") if args.loso_seasons else None
        result = run_reversion_sweep(args.training_set, extra_seasons=extra)

        print()
        print("=" * 78)
        print("  ELO SEASON-REVERSION SWEEP — mean held-out log loss across "
              f"{len(result['clean_seasons'])} clean seasons")
        print("=" * 78)
        print(f"{'Reversion':>12}{'Mean log loss':>16}{'Mean Brier':>13}")
        print("-" * 78)
        for r in result["results"]:
            tag = "  <- current production value" if abs(r["reversion"] - 1/3) < 1e-9 else ""
            best_tag = "  *** BEST ***" if r is result["best"] else ""
            print(f"{r['reversion']:>12.3f}{r['mean_log_loss']:>16.4f}"
                  f"{r['mean_brier']:>13.4f}{tag}{best_tag}")
        print("-" * 78)

        best, current = result["best"], result["current_production_value"]
        gap = current["mean_log_loss"] - best["mean_log_loss"]
        print()
        if abs(best["reversion"] - 1/3) < 1e-9:
            print("  Current production value (1/3) IS the best-performing one tested.")
            print("  No change indicated.")
        elif gap < 0.0005:
            print(f"  Best value ({best['reversion']:.3f}) barely beats the current 1/3 "
                  f"({gap:.4f} log loss) —")
            print("  within noise. Not worth changing on this evidence alone.")
        else:
            print(f"  Best value tested: {best['reversion']:.3f} "
                  f"(beats current 1/3 by {gap:.4f} mean log loss).")
            print("  Worth considering as the new production SEASON_REVERSION — but this")
            print("  is 6 seasons of evidence, not a large sample; treat as a lead, not proof.")
        return 0

    if args.loso:
        candidate = args.candidate or "logreg"
        extra = args.loso_seasons.split(",") if args.loso_seasons else None
        result = run_loso(args.training_set, candidate, extra_seasons=extra)

        print()
        print("=" * 92)
        print("  LEAVE-ONE-SEASON-OUT — does the candidate beat Elo in EVERY season, not just one?")
        print("=" * 92)
        print(f"{'Season':<12}{'n':>6}{'xG log loss':>14}{'Elo log loss':>15}"
              f"{'xG Brier':>11}{'Elo Brier':>11}{'Beats Elo':>12}")
        print("-" * 92)
        for s in result["per_season"]:
            verdict = "PASS" if (s["beats_elo_log_loss"] and s["beats_elo_brier"]) else "fail"
            tag = " *" if s["anomalous"] else ""
            print(f"{s['season'] + tag:<12}{s['n_test']:>6}{s['candidate_log_loss']:>14.4f}"
                  f"{s['elo_log_loss']:>15.4f}{s['candidate_brier']:>11.4f}"
                  f"{s['elo_brier']:>11.4f}{verdict:>12}")
        print("-" * 92)
        summ = result["summary"]
        print(f"\n  * = anomalous season (COVID-shortened / realigned) — excluded from the summary below")
        print(f"  Beats Elo on BOTH metrics: {summ['n_beats_elo_both_metrics']} / "
              f"{summ['n_seasons_clean']} clean seasons")
        print(f"  Mean log-loss gap (Elo − xG, +ve = xG ahead): {summ['mean_log_loss_gap']:+.4f}")
        print()
        if summ["n_beats_elo_both_metrics"] == summ["n_seasons_clean"]:
            print("  Beats Elo in EVERY clean season tested — a repeatable edge, not a one-season result.")
        elif summ["n_beats_elo_both_metrics"] == 0:
            print("  Never beats Elo on a clean season — the single held-out-season pass this")
            print("  model shipped on does not generalize. Treat 'beats Elo' as unproven.")
        else:
            print(f"  Beats Elo in {summ['n_beats_elo_both_metrics']} of {summ['n_seasons_clean']} clean "
                  f"seasons — an inconsistent edge. The single-season gate result this model")
            print("  shipped on is not representative of every season; do not treat it as settled.")
        return 0

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
