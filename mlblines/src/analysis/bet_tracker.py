"""
MLB Bet Tracker - Track recommended bets and their actual outcomes.
Validates model performance over time.
"""

import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
from src.data.mlb_data import fetch_season_games
from src.analysis.analysis_history import get_all_bets_from_history


BET_LOG_PATH = Path(__file__).parent.parent.parent / "mlbdata" / "bet_results.json"


def check_results(days_back=7):
    """Check results of past bets against actual game results."""
    print(f"Loading bets from analysis history (last {days_back} days)...")
    all_bets = get_all_bets_from_history(days_back=days_back)

    if not all_bets:
        print("No bets found in analysis history.")
        return

    print(f"Found {len(all_bets)} bets to check")

    # Always rebuild from scratch to fix any past errors
    results_log = {"results": {}}

    print(f"Fetching game results from last {days_back} days...")
    games = fetch_season_games(days_back=days_back)

    # Build game results keyed by (date, matchup) to handle series correctly
    game_results = {}
    for game in games:
        date = game["date"][:10]
        home = game["home_team"]
        away = game["away_team"]
        game_key = f"{away} @ {home}"
        date_key = f"{date}_{game_key}"

        game_results[date_key] = {
            "date": date,
            "home_score": game["home_score"],
            "away_score": game["away_score"],
            "total": game["total_runs"],
            "home_won": game["home_win"],
            "away_won": not game["home_win"],
        }

    updated = 0
    for bet in all_bets:
        game_key = bet["game"]
        # Extract the date from the analysis timestamp (bets are for that day's games)
        analysis_ts = bet.get("analysis_timestamp", "")
        bet_date = analysis_ts[:10] if analysis_ts else ""

        # Include date in bet_id to distinguish same-matchup bets across days
        bet_id = f"{bet_date}_{game_key}_{bet['pick']}"

        date_key = f"{bet_date}_{game_key}"
        if date_key not in game_results:
            continue

        result = game_results[date_key]
        outcome = _check_bet_result(bet, result)

        if outcome is None:
            continue

        if outcome == "push":
            profit = 0.0
            result_label = "push"
        elif outcome:
            from src.data.odds_fetcher import american_to_decimal
            decimal_odds = american_to_decimal(bet["odds"])
            profit = bet["stake"] * (decimal_odds - 1)
            result_label = "won"
        else:
            profit = -bet["stake"]
            result_label = "lost"

        results_log["results"][bet_id] = {
            "bet": bet,
            "result": result_label,
            "profit": profit,
            "game_result": result,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        updated += 1

    BET_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    BET_LOG_PATH.write_text(json.dumps(results_log, indent=2, default=str))
    print(f"  Updated {updated} bet results")

    _print_performance_summary(results_log["results"])


def _check_bet_result(bet, result):
    """Check if a bet won. Returns True/False/'push'/None."""
    pick = bet["pick"]
    bet_type = bet["bet_type"]

    if bet_type == "Moneyline":
        team = pick.split(" ")[0]
        game = bet["game"]
        parts = game.split(" @ ")
        if len(parts) == 2:
            away_team = parts[0]
            home_team = parts[1]
            if team == away_team:
                return result["away_won"]
            elif team == home_team:
                return result["home_won"]
        # Fallback: check if team is in the away or home position
        if team in game.split(" @ ")[0]:
            return result["away_won"]
        else:
            return result["home_won"]

    elif bet_type == "Total":
        parts = pick.split(" ")
        over_under = parts[0].lower()
        line = float(parts[1])

        if result["total"] == line:
            return "push"

        if over_under == "over":
            return result["total"] > line
        else:
            return result["total"] < line

    elif bet_type == "Run Line":
        return None  # Not implemented yet

    return None


def _print_performance_summary(results):
    """Print performance summary."""
    if not results:
        print("\nNo resolved bets yet.")
        return

    resolved = list(results.values())
    won = [r for r in resolved if r["result"] == "won"]
    lost = [r for r in resolved if r["result"] == "lost"]

    total_staked = sum(r["bet"]["stake"] for r in resolved)
    total_profit = sum(r["profit"] for r in resolved)
    roi = (total_profit / total_staked) if total_staked > 0 else 0

    print(f"\n  Performance: {len(won)}W-{len(lost)}L "
          f"({len(won)/len(resolved):.1%}) | "
          f"Staked: ${total_staked:.2f} | "
          f"Profit: ${total_profit:+.2f} | ROI: {roi:+.1%}")


def get_performance_stats():
    """Get performance statistics for display."""
    if not BET_LOG_PATH.exists():
        return None

    results_log = json.loads(BET_LOG_PATH.read_text())
    results = results_log.get("results", {})

    if not results:
        return None

    resolved = list(results.values())

    def get_grade(edge):
        if edge >= 0.07: return "A"
        elif edge >= 0.04: return "B+"
        elif edge >= 0.03: return "B"
        else: return "C+"

    won = [r for r in resolved if r["result"] == "won"]
    total_staked = sum(r["bet"]["stake"] for r in resolved)
    total_profit = sum(r["profit"] for r in resolved)

    grades = {}
    for r in resolved:
        grade = get_grade(r["bet"]["edge"])
        if grade not in grades:
            grades[grade] = {"bets": [], "won": 0, "staked": 0, "profit": 0}
        grades[grade]["bets"].append(r)
        grades[grade]["staked"] += r["bet"]["stake"]
        grades[grade]["profit"] += r["profit"]
        if r["result"] == "won":
            grades[grade]["won"] += 1

    return {
        "total_bets": len(resolved),
        "won": len(won),
        "lost": len(resolved) - len(won),
        "win_rate": len(won) / len(resolved) if resolved else 0,
        "total_staked": total_staked,
        "total_profit": total_profit,
        "roi": total_profit / total_staked if total_staked > 0 else 0,
        "by_grade": grades,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="MLB Bet Tracker")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()

    if args.check:
        check_results(days_back=args.days)
    else:
        print("Use --check to check past bet results")
