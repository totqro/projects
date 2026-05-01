#!/usr/bin/env python3
"""
NHL Model Backtest
==================
Runs the prediction model retrospectively on completed NHL games to evaluate
accuracy on game winner and total goals predictions.

Usage:
    python backtest.py                    # Backtest since March 1
    python backtest.py --start 2026-02-01 # Custom start date
"""

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.data.nhl_data import fetch_season_games, fetch_standings, get_team_recent_form
from src.models.model import find_similar_games, estimate_probabilities

EST = timezone(timedelta(hours=-4))


def run_backtest(start_date: str = "2026-03-01"):
    print(f"NHL Model Backtest — Games since {start_date}")
    print("=" * 60)

    print("Fetching season games (200-day lookback for training history)...")
    all_games = fetch_season_games(days_back=200)
    standings = fetch_standings()

    if not all_games:
        print("No games found.")
        return None

    print(f"Loaded {len(all_games)} total games, {len(standings)} teams in standings")

    target_games = [g for g in all_games if g["date"][:10] >= start_date and
                    g.get("home_score") is not None and g.get("away_score") is not None]
    print(f"Target games to backtest: {len(target_games)}\n")

    results = []
    skipped = 0

    for game in target_games:
        game_date = game["date"][:10]
        home = game["home_team"]
        away = game["away_team"]
        actual_home_score = game.get("home_score", 0)
        actual_away_score = game.get("away_score", 0)
        actual_total = actual_home_score + actual_away_score
        actual_home_won = actual_home_score > actual_away_score

        # Only use games strictly before this date for training
        prior_games = [g for g in all_games if g["date"][:10] < game_date]

        if len(prior_games) < 30:
            skipped += 1
            continue

        if home not in standings or away not in standings:
            skipped += 1
            continue

        team_forms = {}
        for team in [home, away]:
            team_forms[team] = get_team_recent_form(team, prior_games, n=10)

        similar = find_similar_games(home, away, standings, prior_games, team_forms, n_similar=30)

        if not similar:
            skipped += 1
            continue

        probs = estimate_probabilities(similar, home, away)

        predicted_home_win = probs["home_win_prob"] > 0.5
        predicted_total = probs["expected_total"]
        winner_correct = predicted_home_win == actual_home_won
        total_error = abs(predicted_total - actual_total)

        result = {
            "date": game_date,
            "game": f"{away} @ {home}",
            "home": home,
            "away": away,
            "predicted_home_win_prob": round(probs["home_win_prob"], 3),
            "predicted_away_win_prob": round(probs["away_win_prob"], 3),
            "predicted_winner": home if predicted_home_win else away,
            "actual_winner": home if actual_home_won else away,
            "winner_correct": winner_correct,
            "predicted_total": round(predicted_total, 2),
            "actual_total": actual_total,
            "total_error": round(total_error, 2),
            "actual_score": f"{actual_away_score}-{actual_home_score}",
            "confidence": round(probs["confidence"], 3),
            "n_similar": len(similar),
        }
        results.append(result)

        icon = "✅" if winner_correct else "❌"
        print(f"  {icon} {game_date}: {away} @ {home} | "
              f"Pred: {result['predicted_winner']} ({probs['home_win_prob']:.0%}) | "
              f"Actual: {result['actual_winner']} {actual_away_score}-{actual_home_score} | "
              f"Total pred {predicted_total:.1f} / actual {actual_total}")

    if not results:
        print("\nNo results — not enough historical data for the date range.")
        return None

    correct = sum(1 for r in results if r["winner_correct"])
    total = len(results)
    avg_total_error = sum(r["total_error"] for r in results) / total
    within_1 = sum(1 for r in results if r["total_error"] <= 1) / total
    within_2 = sum(1 for r in results if r["total_error"] <= 2) / total

    print("\n" + "=" * 60)
    print(f"BACKTEST SUMMARY — {total} games backtested, {skipped} skipped")
    print(f"  Winner accuracy:       {correct}/{total} ({correct/total:.1%})")
    print(f"  Avg total goals error: {avg_total_error:.2f} goals")
    print(f"  Total within 1 goal:   {within_1:.1%}")
    print(f"  Total within 2 goals:  {within_2:.1%}")
    print("=" * 60)

    output = {
        "generated_at": datetime.now(EST).isoformat(),
        "start_date": start_date,
        "total_games": total,
        "skipped": skipped,
        "winner_correct": correct,
        "winner_accuracy": round(correct / total, 4),
        "avg_total_error": round(avg_total_error, 3),
        "within_1_goal": round(within_1, 4),
        "within_2_goals": round(within_2, 4),
        "results": sorted(results, key=lambda r: r["date"], reverse=True),
    }

    out_path = Path(__file__).parent / "data" / "backtest_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2))
    print(f"\nSaved to {out_path}")

    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NHL Model Backtest")
    parser.add_argument("--start", default="2026-03-01",
                        help="Start date YYYY-MM-DD (default: 2026-03-01)")
    args = parser.parse_args()
    run_backtest(start_date=args.start)
