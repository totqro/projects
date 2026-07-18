"""
Elo + home-ice logistic regression baseline.

This is the standard dumb baseline for NHL win prediction. Any model that
can't beat it out-of-sample on log loss / Brier score (not win rate on a
cherry-picked bet sample) has no business being shipped.

Elo update, per game, in chronological order across ALL games (not just the
point-in-time-filtered training rows — Elo needs every result to track team
strength):

    expected_home = 1 / (1 + 10^(-(elo_home - elo_away) / 400))
    elo_home += K * (actual_home_win - expected_home)
    elo_away -= K * (actual_home_win - expected_home)

No home-ice boost is baked into the Elo update itself — home advantage is
estimated explicitly as a coefficient in the downstream logistic regression,
so it's visible and reportable rather than a buried constant. Elo carries
across seasons with regression to the mean (1/3 reversion to 1500) at each
season boundary, matching the standard 538-style NHL/NFL Elo treatment.

The logistic regression has 5 parameters:
    intercept, elo_diff, rest_diff, home_b2b, away_b2b

elo_diff alone is essentially a single-parameter model; rest/b2b add the
other well-established, cheap-to-compute situational factors (schedule spot)
without requiring 52 leakage-prone features.
"""

import csv
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, log_loss, brier_score_loss

from src.data.historical_dataset import fetch_season_games_full

INITIAL_ELO = 1500.0
K_FACTOR = 6.0
SEASON_REVERSION = 1.0 / 3.0  # fraction reverted toward 1500 at season start

ELO_FEATURE_COLUMNS = ["elo_diff", "rest_diff", "home_b2b", "away_b2b"]


def _run_elo(all_games: list):
    """
    Walk every completed game in chronological order, applying the Elo update
    and season-boundary reversion. Returns (pregame, final_ratings,
    last_season) where pregame is {game_id: (home_elo_pre, away_elo_pre)} and
    final_ratings/last_season are the post-last-game state per team — the raw
    material both compute_pregame_elo() (training) and compute_live_ratings()
    (serving) are built from, so the two never drift apart.
    """
    games = sorted(all_games, key=lambda g: (g["date"], g["id"]))

    ratings = {}          # team -> elo
    last_season = {}       # team -> season last seen in
    pregame = {}

    for g in games:
        season = g["season"]
        home, away = g["home_team"], g["away_team"]

        for team in (home, away):
            if team not in ratings:
                ratings[team] = INITIAL_ELO
                last_season[team] = season
            elif last_season[team] != season:
                ratings[team] += (INITIAL_ELO - ratings[team]) * SEASON_REVERSION
                last_season[team] = season

        elo_home, elo_away = ratings[home], ratings[away]
        pregame[g["id"]] = (elo_home, elo_away)

        expected_home = 1.0 / (1.0 + 10 ** (-(elo_home - elo_away) / 400.0))
        actual_home = 1.0 if g["home_win"] else 0.0
        delta = K_FACTOR * (actual_home - expected_home)
        ratings[home] = elo_home + delta
        ratings[away] = elo_away - delta

    return pregame, ratings, last_season


def compute_pregame_elo(all_games: list) -> dict:
    """
    Walk every completed game in chronological order and return
    {game_id: (home_elo_pre, away_elo_pre)} — the rating BEFORE that game,
    i.e. the only Elo values legitimately usable as a pregame feature.
    """
    pregame, _, _ = _run_elo(all_games)
    return pregame


def compute_live_ratings(all_games: list, current_season: str) -> dict:
    """
    Serving-time counterpart to compute_pregame_elo(): the rating for each
    team AFTER the last completed game in `all_games`, i.e. the pregame Elo
    for that team's next (not-yet-played) game. If a team's last game was in
    a season other than `current_season` (offseason gap or a team that
    hasn't played yet this season), the same season-boundary reversion used
    mid-training is applied here too, so a live prediction on day 1 of a
    season sees the same reverted rating a training row would have.
    """
    _, ratings, last_season = _run_elo(all_games)
    live = {}
    for team, rating in ratings.items():
        if last_season.get(team) != current_season:
            rating = rating + (INITIAL_ELO - rating) * SEASON_REVERSION
        live[team] = rating
    return live


def build_elo_rows(seasons: list, training_set_csv: str = "data/training_set.csv") -> list:
    """
    Compute pregame Elo over the FULL schedule of `seasons` (every game, no
    min-GP filtering — Elo needs the early-season games to be accurate), then
    join elo_diff onto the same point-in-time rows used for the ML model
    (read from `training_set_csv`) so the two are compared on an identical
    row set. rest_diff / home_b2b / away_b2b are reused as-is from that file.
    """
    all_games = []
    for season in seasons:
        all_games.extend(fetch_season_games_full(season, verbose=False))
    pregame_elo = compute_pregame_elo(all_games)

    with open(training_set_csv) as f:
        rows = list(csv.DictReader(f))

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


def evaluate(seasons: list, training_set_csv: str = "data/training_set.csv") -> dict:
    """
    Time-split evaluation matching build_training_set.py's ML validation:
    train on all seasons but the most recent, test on the most recent.
    Returns metrics dict and the fitted coefficients.
    """
    rows = build_elo_rows(seasons, training_set_csv)
    all_seasons = sorted(set(r["season"] for r in rows))
    if len(all_seasons) < 2:
        raise ValueError("Need at least 2 seasons to evaluate the Elo baseline")
    test_season = all_seasons[-1]

    train = [r for r in rows if r["season"] != test_season]
    test = [r for r in rows if r["season"] == test_season]

    def to_xy(subset):
        X = np.array([[r[c] for c in ELO_FEATURE_COLUMNS] for r in subset])
        y = np.array([r["home_win"] for r in subset])
        return X, y

    X_train, y_train = to_xy(train)
    X_test, y_test = to_xy(test)

    scaler = StandardScaler().fit(X_train)
    # liblinear avoids a spurious "divide by zero encountered in matmul"
    # RuntimeWarning that lbfgs triggers under this environment's BLAS
    # (numpy/Accelerate) despite producing identical, correct results.
    model = LogisticRegression(max_iter=2000, solver="liblinear")
    model.fit(scaler.transform(X_train), y_train)
    probs = model.predict_proba(scaler.transform(X_test))[:, 1]

    # Un-scale coefficients back to original feature units (elo points, days,
    # 0/1 flags) so they're directly interpretable.
    raw_coef = model.coef_[0] / scaler.scale_
    raw_intercept = model.intercept_[0] - np.sum(model.coef_[0] * scaler.mean_ / scaler.scale_)
    coefs = dict(zip(ELO_FEATURE_COLUMNS, raw_coef))
    coefs["intercept"] = raw_intercept

    return {
        "test_season": test_season,
        "n_train": len(train),
        "n_test": len(test),
        "accuracy": accuracy_score(y_test, probs > 0.5),
        "log_loss": log_loss(y_test, probs),
        "brier": brier_score_loss(y_test, probs),
        "coefficients": coefs,
        "model": model,
        "scaler": scaler,
    }


if __name__ == "__main__":
    seasons = ["20222023", "20232024", "20242025", "20252026"]
    result = evaluate(seasons)
    print(f"Elo + home-ice logistic regression baseline")
    print(f"Train: {result['n_train']} games, Test ({result['test_season']}): {result['n_test']} games")
    print(f"Accuracy: {result['accuracy']:.3f}  Log loss: {result['log_loss']:.4f}  "
          f"Brier: {result['brier']:.4f}")
    print("Coefficients:")
    for name, w in result["coefficients"].items():
        print(f"  {name:<12} {w:+.4f}")
