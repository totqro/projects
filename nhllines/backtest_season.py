#!/usr/bin/env python3
"""
Season Backtest — test model calibration on ~600+ historical games.

Uses cached game data (Nov 2025 - Apr 2026). For each game:
1. Uses only data available BEFORE that game (no lookahead)
2. Runs the similarity model to predict home win probability
3. Compares prediction to actual outcome
4. Measures calibration, Brier score, and simulated profit

No odds data needed — tests the core prediction engine.
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict, deque


def load_all_cached_games():
    """Load and deduplicate games from all cache files."""
    cache_dir = Path("cache")
    all_games = {}

    for f in sorted(cache_dir.glob("season_games_*.json")):
        data = json.loads(f.read_text())
        for g in data:
            key = f'{g["date"][:10]}_{g["home_team"]}_{g["away_team"]}'
            all_games[key] = g

    games = sorted(all_games.values(), key=lambda g: g["date"])
    return games


def build_form_index(games, n=10):
    """Build point-in-time form index (same logic as model.py)."""
    from collections import deque

    default_form = {"win_pct": 0.5, "avg_gf": 3.0, "avg_ga": 3.0, "points_pct": 0.5}
    form_index = {}
    team_history = {}

    # Group by date
    games_by_date = defaultdict(list)
    for g in games:
        games_by_date[g["date"][:10]].append(g)

    for date in sorted(games_by_date.keys()):
        date_games = games_by_date[date]

        # Snapshot current form for all teams BEFORE today's games
        for g in date_games:
            for team in [g["home_team"], g["away_team"]]:
                history = team_history.get(team)
                if history and len(history) > 0:
                    wins = sum(r[0] for r in history)
                    gf = sum(r[1] for r in history)
                    ga = sum(r[2] for r in history)
                    ng = len(history)
                    form_index[(team, date)] = {
                        "win_pct": wins / ng,
                        "avg_gf": gf / ng,
                        "avg_ga": ga / ng,
                        "points_pct": wins / ng,
                    }
                else:
                    form_index[(team, date)] = default_form

        # Now update history with today's results
        for g in date_games:
            home = g["home_team"]
            away = g["away_team"]
            home_win = g.get("home_win", False)
            h_gf = g.get("home_score", 0) or 0
            h_ga = g.get("away_score", 0) or 0

            if home not in team_history:
                team_history[home] = deque(maxlen=n)
            team_history[home].append((1 if home_win else 0, h_gf, h_ga))

            if away not in team_history:
                team_history[away] = deque(maxlen=n)
            team_history[away].append((0 if home_win else 1, h_ga, h_gf))

    return form_index


def calculate_similarity(home_stats, away_stats, hist_home_stats, hist_away_stats,
                         game, home_team, away_team):
    """Simplified similarity calculation (matches model.py logic)."""
    weights = {
        "team_quality_gap": 3.0,
        "home_offense": 2.0,
        "home_defense": 2.0,
        "away_offense": 2.0,
        "away_defense": 2.0,
        "same_teams": 2.0,
        "points_pct": 2.0,
    }

    total_weight = sum(weights.values())

    # Team quality gap
    current_gap = home_stats["win_pct"] - away_stats["win_pct"]
    hist_gap = hist_home_stats["win_pct"] - hist_away_stats["win_pct"]
    gap_diff = abs(current_gap - hist_gap)
    gap_sim = max(0, 1.0 - gap_diff * 2.5)

    # Offense
    home_off_diff = abs(home_stats["avg_gf"] - hist_home_stats["avg_gf"])
    home_off_sim = max(0, 1.0 - home_off_diff / 2.0)

    away_off_diff = abs(away_stats["avg_gf"] - hist_away_stats["avg_gf"])
    away_off_sim = max(0, 1.0 - away_off_diff / 2.0)

    # Defense
    home_def_diff = abs(home_stats["avg_ga"] - hist_home_stats["avg_ga"])
    home_def_sim = max(0, 1.0 - home_def_diff / 2.0)

    away_def_diff = abs(away_stats["avg_ga"] - hist_away_stats["avg_ga"])
    away_def_sim = max(0, 1.0 - away_def_diff / 2.0)

    # Same teams bonus
    hist_home = game["home_team"]
    hist_away = game["away_team"]
    if hist_home == home_team and hist_away == away_team:
        same_teams_sim = 1.0
    elif hist_home == away_team and hist_away == home_team:
        same_teams_sim = 0.5
    else:
        same_teams_sim = 0.0

    # Points pct
    home_pp_diff = abs(home_stats.get("points_pct", 0.5) - hist_home_stats.get("points_pct", 0.5))
    away_pp_diff = abs(away_stats.get("points_pct", 0.5) - hist_away_stats.get("points_pct", 0.5))
    pp_sim = max(0, 1.0 - (home_pp_diff + away_pp_diff) * 2.0)

    similarity = (
        weights["team_quality_gap"] * gap_sim +
        weights["home_offense"] * home_off_sim +
        weights["home_defense"] * home_def_sim +
        weights["away_offense"] * away_off_sim +
        weights["away_defense"] * away_def_sim +
        weights["same_teams"] * same_teams_sim +
        weights["points_pct"] * pp_sim
    ) / total_weight

    return similarity


def predict_game(home_team, away_team, game_date, past_games, form_index):
    """Predict home win probability using similarity model."""
    default_form = {"win_pct": 0.5, "avg_gf": 3.0, "avg_ga": 3.0, "points_pct": 0.5}

    home_form = form_index.get((home_team, game_date), default_form)
    away_form = form_index.get((away_team, game_date), default_form)

    # Use form as both "standings" and "form" (simplified — no separate standings API needed)
    home_stats = home_form
    away_stats = away_form

    # Find similar games from past_games only
    scored_games = []
    game_dt = datetime.strptime(game_date, "%Y-%m-%d")

    for game in past_games:
        gd = game["date"][:10]
        hist_home_stats = form_index.get((game["home_team"], gd), default_form)
        hist_away_stats = form_index.get((game["away_team"], gd), default_form)

        similarity = calculate_similarity(
            home_stats, away_stats,
            hist_home_stats, hist_away_stats,
            game, home_team, away_team,
        )

        # Time decay (45-day half-life)
        try:
            hist_dt = datetime.strptime(gd, "%Y-%m-%d")
            days_ago = (game_dt - hist_dt).days
            if days_ago < 0:
                continue  # Skip future games (shouldn't happen but safety check)
            recency = 0.8 + 0.2 * (0.5 ** (days_ago / 45.0))
            similarity *= recency
        except ValueError:
            continue

        if similarity >= 0.55:
            scored_games.append((game, similarity))

    scored_games.sort(key=lambda x: x[1], reverse=True)
    similar = scored_games[:50]

    if not similar:
        return 0.5, 0.0  # No data, low confidence

    # Weighted probability
    total_weight = 0
    weighted_wins = 0
    for game, sim in similar:
        w = sim ** 2
        total_weight += w
        if game.get("home_win"):
            weighted_wins += w

    home_win_prob = weighted_wins / total_weight if total_weight > 0 else 0.5

    # Confidence (simplified)
    top5_avg = sum(s for _, s in similar[:5]) / min(5, len(similar))
    confidence = min(0.87, 0.25 + 0.65 * ((top5_avg - 0.55) / 0.45))
    confidence = max(0.25, confidence)

    # Regression to mean
    regression_strength = 0.55 + 0.40 * ((confidence - 0.25) / 0.62)
    home_win_prob = home_win_prob * regression_strength + 0.5 * (1 - regression_strength)

    return home_win_prob, confidence


def main():
    print("Loading cached game data...")
    all_games = load_all_cached_games()
    dates = sorted(set(g["date"][:10] for g in all_games))
    print(f"  {len(all_games)} games, {dates[0]} to {dates[-1]}")

    print("\nBuilding form index...")
    form_index = build_form_index(all_games)
    print(f"  {len(form_index)} team-date entries")

    # Need at least 30 days of data before we start testing
    MIN_TRAINING_DAYS = 40
    training_cutoff = dates[MIN_TRAINING_DAYS] if len(dates) > MIN_TRAINING_DAYS else dates[-1]
    print(f"\nTraining period: {dates[0]} to {training_cutoff}")
    print(f"Testing period: {training_cutoff} onwards")

    # Run predictions
    predictions = []
    games_by_date = defaultdict(list)
    for g in all_games:
        games_by_date[g["date"][:10]].append(g)

    test_dates = [d for d in dates if d > training_cutoff]
    total_test_games = sum(len(games_by_date[d]) for d in test_dates)
    print(f"Testing on {total_test_games} games across {len(test_dates)} dates\n")

    processed = 0
    for date in test_dates:
        # Games available before this date
        past_games = [g for g in all_games if g["date"][:10] < date]

        for game in games_by_date[date]:
            home = game["home_team"]
            away = game["away_team"]
            actual_home_win = game.get("home_win", False)

            pred_prob, confidence = predict_game(home, away, date, past_games, form_index)

            predictions.append({
                "date": date,
                "home": home,
                "away": away,
                "pred_home_win": pred_prob,
                "actual_home_win": actual_home_win,
                "confidence": confidence,
                "correct": (pred_prob > 0.5 and actual_home_win) or (pred_prob < 0.5 and not actual_home_win),
            })

            processed += 1
            if processed % 100 == 0:
                print(f"  Progress: {processed}/{total_test_games} games...")

    print(f"\n  Completed: {len(predictions)} predictions\n")

    # === ANALYSIS ===
    print("=" * 80)
    print("  SEASON BACKTEST RESULTS")
    print("=" * 80)

    # Overall accuracy
    correct = sum(1 for p in predictions if p["correct"])
    total = len(predictions)
    print(f"\n  Overall Accuracy: {correct}/{total} ({correct/total:.1%})")

    # Brier score
    brier_scores = [(p["pred_home_win"] - (1.0 if p["actual_home_win"] else 0.0)) ** 2 for p in predictions]
    avg_brier = sum(brier_scores) / len(brier_scores)
    print(f"  Brier Score: {avg_brier:.4f} (lower is better, 0.25 = coin flip)")

    # Calibration by probability bin
    print("\n  CALIBRATION BY PREDICTED PROBABILITY:")
    print("  " + "-" * 70)
    bins = defaultdict(lambda: {"correct": 0, "total": 0, "sum_pred": 0})
    for p in predictions:
        # Use the stronger side's probability for binning
        prob = max(p["pred_home_win"], 1 - p["pred_home_win"])
        bin_key = int(prob * 20) * 5  # 5% bins
        won = p["correct"]
        bins[bin_key]["total"] += 1
        bins[bin_key]["sum_pred"] += prob
        if won:
            bins[bin_key]["correct"] += 1

    for bin_key in sorted(bins.keys()):
        data = bins[bin_key]
        if data["total"] < 5:
            continue
        predicted = data["sum_pred"] / data["total"]
        actual = data["correct"] / data["total"]
        diff = actual - predicted
        bar = "█" * int(actual * 30)
        print(f"    {bin_key:3d}%: {actual:.1%} actual ({data['correct']:3d}/{data['total']:3d}) "
              f"vs {predicted:.1%} predicted [{diff:+.1%}] {bar}")

    # Calibration by confidence
    print("\n  ACCURACY BY CONFIDENCE LEVEL:")
    print("  " + "-" * 70)
    conf_bins = defaultdict(lambda: {"correct": 0, "total": 0})
    for p in predictions:
        conf = p["confidence"]
        if conf >= 0.75:
            cb = "75%+"
        elif conf >= 0.70:
            cb = "70-75%"
        elif conf >= 0.60:
            cb = "60-70%"
        elif conf >= 0.50:
            cb = "50-60%"
        else:
            cb = "<50%"
        conf_bins[cb]["total"] += 1
        if p["correct"]:
            conf_bins[cb]["correct"] += 1

    for label in ["75%+", "70-75%", "60-70%", "50-60%", "<50%"]:
        if label not in conf_bins:
            continue
        data = conf_bins[label]
        wr = data["correct"] / data["total"] if data["total"] else 0
        print(f"    {label:8s}: {data['correct']:3d}/{data['total']:3d} ({wr:.1%})")

    # Simulated betting: if we bet on any game where model predicts >X% for one side
    print("\n  SIMULATED BETTING (flat $1 bets at -110 odds):")
    print("  " + "-" * 70)

    for threshold in [0.52, 0.55, 0.58, 0.60, 0.62, 0.65]:
        bets = [p for p in predictions if max(p["pred_home_win"], 1 - p["pred_home_win"]) >= threshold]
        if not bets:
            continue
        wins = sum(1 for p in bets if p["correct"])
        losses = len(bets) - wins
        # At -110, need 52.4% to break even
        # Win pays $0.909, loss costs $1.00
        profit = wins * 0.909 - losses * 1.0
        roi = profit / len(bets) if bets else 0
        print(f"    Threshold {threshold:.0%}: {wins}W-{losses}L ({wins/len(bets):.1%}) "
              f"| Profit: ${profit:+.2f} | ROI: {roi:+.1%}")

    # Same but with confidence filter
    print("\n  SIMULATED BETTING (probability + confidence filters):")
    print("  " + "-" * 70)

    for prob_thresh in [0.55, 0.58, 0.60]:
        for conf_thresh in [0.50, 0.60, 0.70, 0.75]:
            bets = [p for p in predictions
                    if max(p["pred_home_win"], 1 - p["pred_home_win"]) >= prob_thresh
                    and p["confidence"] >= conf_thresh]
            if len(bets) < 10:
                continue
            wins = sum(1 for p in bets if p["correct"])
            losses = len(bets) - wins
            profit = wins * 0.909 - losses * 1.0
            roi = profit / len(bets) if bets else 0
            label = f"prob≥{prob_thresh:.0%} conf≥{conf_thresh:.0%}"
            print(f"    {label:22s}: {wins:3d}W-{losses:3d}L ({wins/len(bets):.1%}) "
                  f"| P=${profit:+6.2f} | ROI={roi:+.1%} | N={len(bets)}")

    # Home vs Away accuracy
    print("\n  HOME vs AWAY PREDICTION ACCURACY:")
    print("  " + "-" * 70)
    home_picks = [p for p in predictions if p["pred_home_win"] > 0.5]
    away_picks = [p for p in predictions if p["pred_home_win"] < 0.5]
    if home_picks:
        hw = sum(1 for p in home_picks if p["correct"])
        print(f"    Predicted Home Win: {hw}/{len(home_picks)} ({hw/len(home_picks):.1%})")
    if away_picks:
        aw = sum(1 for p in away_picks if p["correct"])
        print(f"    Predicted Away Win: {aw}/{len(away_picks)} ({aw/len(away_picks):.1%})")

    # Monthly breakdown
    print("\n  MONTHLY ACCURACY:")
    print("  " + "-" * 70)
    monthly = defaultdict(lambda: {"correct": 0, "total": 0})
    for p in predictions:
        month = p["date"][:7]
        monthly[month]["total"] += 1
        if p["correct"]:
            monthly[month]["correct"] += 1
    for month in sorted(monthly.keys()):
        data = monthly[month]
        wr = data["correct"] / data["total"]
        print(f"    {month}: {data['correct']}/{data['total']} ({wr:.1%})")

    # Save results
    output = {
        "total_games": total,
        "accuracy": correct / total,
        "brier_score": avg_brier,
        "predictions": predictions,
    }
    Path("data/backtest_results.json").write_text(json.dumps(output, indent=2, default=str))
    print(f"\n  Results saved to data/backtest_results.json")
    print("=" * 80)


if __name__ == "__main__":
    main()
