"""
Bet Tracker - Track recommended bets and their actual outcomes
Helps validate model performance over time.
Uses analysis_history.json as the source of truth for all bets.
"""

import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

# EST = UTC-4
EST = timezone(timedelta(hours=-4))
from src.data.nhl_data import fetch_season_games
from src.analysis.analysis_history import get_all_bets_from_history


BET_LOG_PATH = Path(__file__).parent.parent.parent / "data" / "bet_results.json"


def check_results(days_back: int = 7):
    """
    Check results of past bets from analysis history and calculate actual performance.
    
    Args:
        days_back: How many days back to check results for
    """
    # Get all bets from analysis history
    print(f"Loading bets from analysis history (last {days_back} days)...")
    all_bets = get_all_bets_from_history(days_back=days_back)
    
    if not all_bets:
        print("No bets found in analysis history.")
        return
    
    print(f"Found {len(all_bets)} bets to check")
    
    # Load existing results
    if BET_LOG_PATH.exists():
        results_log = json.loads(BET_LOG_PATH.read_text())
    else:
        results_log = {"results": {}}
    
    # Fetch recent game results
    print(f"Fetching game results from last {days_back} days...")
    games = fetch_season_games(days_back=days_back)
    
    # Create lookup dict: game_key -> result
    game_results = {}
    for game in games:
        date = game["date"][:10]
        home = game["home_team"]
        away = game["away_team"]
        game_key = f"{away} @ {home}"
        
        game_results[game_key] = {
            "date": date,
            "home_score": game["home_score"],
            "away_score": game["away_score"],
            "total": game["home_score"] + game["away_score"],
            "home_won": game["home_score"] > game["away_score"],
            "away_won": game["away_score"] > game["home_score"],
        }
    
    # Check each bet
    updated = 0
    for bet in all_bets:
        # Create unique bet ID based on game and pick (not timestamp)
        # This prevents duplicates from multiple analyses
        bet_id = f"{bet['game']}_{bet['pick']}"
        
        # Skip if already resolved
        if bet_id in results_log["results"]:
            continue
        
        game_key = bet["game"]
        if game_key not in game_results:
            continue
        
        result = game_results[game_key]
        outcome = _check_bet_result(bet, result)

        if outcome is None:
            continue

        # Calculate profit/loss
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

        # Store result
        results_log["results"][bet_id] = {
            "bet": bet,
            "result": result_label,
            "profit": profit,
            "game_result": result,
            "checked_at": datetime.now(EST).isoformat(),
        }
        
        updated += 1
    
    # Save updated results
    BET_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    BET_LOG_PATH.write_text(json.dumps(results_log, indent=2, default=str))
    
    print(f"✅ Updated {updated} bet results")
    
    # Print summary
    _print_performance_summary_from_results(results_log["results"])


def _print_performance_summary_from_results(results: dict):
    """Print summary of bet performance from results log."""
    if not results:
        print("\nNo resolved bets yet.")
        return

    resolved = list(results.values())
    won = [r for r in resolved if r["result"] == "won"]
    lost = [r for r in resolved if r["result"] == "lost"]

    total_staked = sum(r["bet"]["stake"] for r in resolved)
    total_profit = sum(r["profit"] for r in resolved)
    roi = (total_profit / total_staked) if total_staked > 0 else 0

    print(f"\n📊 Performance: {len(won)}W-{len(lost)}L "
          f"({len(won)/len(resolved):.1%}) | "
          f"Staked: ${total_staked:.2f} | "
          f"Profit: ${total_profit:+.2f} | ROI: {roi:+.1%}")


def _check_bet_result(bet: dict, result: dict):
    """
    Check if a bet won based on the actual game result.

    Returns:
        True if won, False if lost, "push" if line lands exactly
    """
    pick = bet["pick"]
    bet_type = bet["bet_type"]

    if bet_type == "Moneyline":
        # Extract team from pick (e.g., "TOR ML" -> "TOR")
        team = pick.split(" ")[0]
        game = bet["game"]

        if team in game.split(" @ ")[0]:  # Away team
            return result["away_won"]
        else:  # Home team
            return result["home_won"]

    elif bet_type == "Total":
        # Extract over/under and line (e.g., "Over 6.5" or "Under 5.5")
        parts = pick.split(" ")
        over_under = parts[0].lower()
        line = float(parts[1])

        # Push: total lands exactly on a whole-number line
        if result["total"] == line:
            return "push"

        if over_under == "over":
            return result["total"] > line
        else:  # under
            return result["total"] < line

    elif bet_type == "Spread":
        # More complex - would need to parse spread
        # For now, return None (not implemented)
        return None
    
    return None


def _print_performance_summary(bets: list):
    """Print summary of bet performance, grouped by grade."""
    resolved = [b for b in bets if b["result"] is not None]
    
    if not resolved:
        print("\nNo resolved bets yet.")
        return
    
    won = [b for b in resolved if b["result"] == "won"]
    lost = [b for b in resolved if b["result"] == "lost"]
    
    total_staked = sum(b["stake"] for b in resolved)
    total_profit = sum(b["profit"] for b in resolved)
    roi = (total_profit / total_staked) if total_staked > 0 else 0
    
    print("\n" + "=" * 75)
    print("  BET PERFORMANCE SUMMARY")
    print("=" * 75)
    print(f"  Total bets tracked: {len(resolved)}")
    print(f"  Won: {len(won)} ({len(won)/len(resolved)*100:.1f}%)")
    print(f"  Lost: {len(lost)} ({len(lost)/len(resolved)*100:.1f}%)")
    print(f"  Total staked: ${total_staked:.2f}")
    print(f"  Total profit: ${total_profit:.2f}")
    print(f"  ROI: {roi:.2%}")
    print("=" * 75)
    
    # Group by grade
    def get_grade(edge):
        if edge >= 0.07:
            return "A"
        elif edge >= 0.04:
            return "B+"
        elif edge >= 0.03:
            return "B"
        else:
            return "C+"
    
    # Add grade to each result
    for r in resolved:
        r["grade"] = get_grade(r["bet"]["edge"])
    
    # Group by grade
    grades = {}
    for r in resolved:
        grade = r["grade"]
        if grade not in grades:
            grades[grade] = []
        grades[grade].append(r)
    
    # Print performance by grade
    print("\n  PERFORMANCE BY GRADE:")
    print("-" * 75)
    
    for grade in ["A", "B+", "B", "C+"]:
        if grade not in grades:
            continue
        
        grade_results = grades[grade]
        grade_won = [r for r in grade_results if r["result"] == "won"]
        grade_staked = sum(r["bet"]["stake"] for r in grade_results)
        grade_profit = sum(r["profit"] for r in grade_results)
        grade_roi = (grade_profit / grade_staked) if grade_staked > 0 else 0
        
        print(f"\n  [{grade:3s}] {len(grade_results)} bets | "
              f"Won: {len(grade_won)} ({len(grade_won)/len(grade_results)*100:.1f}%) | "
              f"Profit: ${grade_profit:+.2f} | ROI: {grade_roi:+.1%}")
        
        # Show recent bets in this grade
        recent = sorted(grade_results, 
                       key=lambda r: r.get("checked_at", ""), 
                       reverse=True)[:5]
        for r in recent:
            result_icon = "✅" if r["result"] == "won" else "❌"
            bet = r["bet"]
            print(f"       {result_icon} {bet['pick']:20s} {bet['game']:20s} "
                  f"${r['profit']:+.2f}")
    
    print("\n" + "=" * 75)


def get_performance_stats():
    """
    Get performance statistics for display.
    
    Returns:
        dict: Performance metrics including grade breakdowns
    """
    if not BET_LOG_PATH.exists():
        return None
    
    results_log = json.loads(BET_LOG_PATH.read_text())
    results = results_log.get("results", {})
    
    if not results:
        return None
    
    resolved = list(results.values())
    
    def get_grade(edge):
        if edge >= 0.07:
            return "A"
        elif edge >= 0.04:
            return "B+"
        elif edge >= 0.03:
            return "B"
        else:
            return "C+"
    
    won = [r for r in resolved if r["result"] == "won"]
    total_staked = sum(r["bet"]["stake"] for r in resolved)
    total_profit = sum(r["profit"] for r in resolved)
    
    # Calculate by grade
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
        "win_rate": len(won) / len(resolved),
        "total_staked": total_staked,
        "total_profit": total_profit,
        "roi": total_profit / total_staked if total_staked > 0 else 0,
        "by_grade": grades,
    }


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Bet Tracker")
    parser.add_argument("--check", action="store_true", 
                       help="Check results of past bets")
    parser.add_argument("--days", type=int, default=7,
                       help="Days back to check (default: 7)")
    args = parser.parse_args()
    
    if args.check:
        check_results(days_back=args.days)
    else:
        print("Use --check to check past bet results")
        print("Example: python bet_tracker.py --check --days 7")
