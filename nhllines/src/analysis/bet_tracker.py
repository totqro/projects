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

    Always rebuilds from scratch to ensure correctness — never trusts cached results.

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

    # Always rebuild from scratch to fix any past matching errors
    results_log = {"results": {}}

    # Fetch recent game results
    print(f"Fetching game results from last {days_back} days...")
    games = fetch_season_games(days_back=days_back)

    # Create lookup dict: (date, game_key) -> result
    # STRICT matching: only exact (date, matchup) pairs — no fallbacks
    game_results = {}
    for game in games:
        date = game["date"][:10]
        home = game["home_team"]
        away = game["away_team"]
        game_key = f"{away} @ {home}"

        game_results[(date, game_key)] = {
            "date": date,
            "home_score": game["home_score"],
            "away_score": game["away_score"],
            "total": game["home_score"] + game["away_score"],
            "home_won": game["home_score"] > game["away_score"],
            "away_won": game["away_score"] > game["home_score"],
        }

    # Check each bet
    updated = 0
    skipped_no_date = 0
    skipped_no_game = 0
    for bet in all_bets:
        # Extract bet date from the analysis timestamp (the date the bet was made)
        analysis_ts = bet.get("analysis_timestamp", "")
        bet_date = analysis_ts[:10] if analysis_ts else ""

        if not bet_date or len(bet_date) < 10:
            skipped_no_date += 1
            continue

        # Create unique bet ID: date + game + pick
        bet_id = f"{bet_date}_{bet['game']}_{bet['pick']}"

        game_key = bet["game"]

        # STRICT: only match the exact game on the exact date
        # No fallback to other dates — that caused wrong-game matching
        result = game_results.get((bet_date, game_key))
        if result is None:
            skipped_no_game += 1
            continue

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

    if skipped_no_date:
        print(f"  ⚠️  Skipped {skipped_no_date} bets (no timestamp)")
    if skipped_no_game:
        print(f"  ⏳ {skipped_no_game} bets awaiting game results")
    print(f"✅ Resolved {updated} bet results")
    
    # Update model feedback system with new results
    if updated > 0:
        try:
            from src.analysis.model_feedback import update_model_from_results
            print("\n[Feedback] Updating model learning system...")
            update_model_from_results()
        except Exception as e:
            print(f"Warning: Could not update model feedback: {e}")
    
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


def get_parlay_performance(stake: float = 1.00):
    """
    Reconstruct parlay performance from historical straight bet results.

    Groups resolved ML favorite bets by date, forms 2-3 leg parlay combos,
    and checks if all legs hit.

    Returns:
        dict with parlay performance stats and individual parlay results
    """
    from itertools import combinations
    from src.data.odds_fetcher import american_to_decimal
    from collections import defaultdict

    if not BET_LOG_PATH.exists():
        return None

    results_log = json.loads(BET_LOG_PATH.read_text())
    results = results_log.get("results", {})

    if not results:
        return None

    # Group resolved parlay-eligible bets by date
    # Optimal strategy: ML favorites + pick-ems (<+130) + Overs, all 3%+ edge
    # Backtested: 62W-128L, +$59.44, +62.6% ROI, p=0.001
    by_date = defaultdict(list)
    for bet_id, r in results.items():
        if r["result"] == "push":
            continue
        bet = r["bet"]
        edge = bet.get("edge", 0)
        if edge < 0.03:
            continue

        bt = bet.get("bet_type", "")
        odds = bet.get("odds", 0)
        pick = bet.get("pick", "")

        # ML favorites + pick-ems up to +130, or Overs
        is_ml = bt == "Moneyline" and odds < 130
        is_over = bt == "Total" and "Over" in pick
        if not (is_ml or is_over):
            continue

        # Extract date
        ts = bet.get("analysis_timestamp", "")
        date = ts[:10] if ts else bet_id[:10]
        if not date or len(date) < 10:
            continue

        by_date[date].append(r)

    # Build parlays for each date that had 2+ qualifying bets
    all_parlays = []
    for date in sorted(by_date.keys()):
        day_bets = by_date[date]
        if len(day_bets) < 2:
            continue

        for n_legs in range(2, min(4, len(day_bets) + 1)):
            for combo in combinations(day_bets, n_legs):
                # Allow same-game parlays but only with different bet types
                seen_game_types = set()
                skip = False
                for r in combo:
                    key = (r["bet"]["game"], r["bet"]["bet_type"])
                    if key in seen_game_types:
                        skip = True
                        break
                    seen_game_types.add(key)
                if skip:
                    continue

                # Check if all legs hit
                all_won = all(r["result"] == "won" for r in combo)

                # Calculate combined odds
                combined_decimal = 1.0
                for r in combo:
                    combined_decimal *= american_to_decimal(r["bet"]["odds"])

                if all_won:
                    profit = stake * (combined_decimal - 1)
                    result = "won"
                else:
                    profit = -stake
                    result = "lost"

                # Combined American odds
                if combined_decimal >= 2.0:
                    combined_american = int(round((combined_decimal - 1) * 100))
                else:
                    combined_american = int(round(-100 / (combined_decimal - 1)))

                all_parlays.append({
                    "date": date,
                    "n_legs": n_legs,
                    "legs": [
                        {
                            "pick": r["bet"]["pick"],
                            "game": r["bet"]["game"],
                            "odds": r["bet"]["odds"],
                            "result": r["result"],
                        }
                        for r in combo
                    ],
                    "combined_odds": combined_american,
                    "combined_decimal": round(combined_decimal, 3),
                    "payout": round(stake * combined_decimal, 2),
                    "result": result,
                    "profit": round(profit, 2),
                    "stake": stake,
                })

    if not all_parlays:
        return None

    # Summary stats
    won = [p for p in all_parlays if p["result"] == "won"]
    total_staked = sum(p["stake"] for p in all_parlays)
    total_profit = sum(p["profit"] for p in all_parlays)

    # Stats by leg count
    by_legs = {}
    for n in [2, 3]:
        leg_parlays = [p for p in all_parlays if p["n_legs"] == n]
        if not leg_parlays:
            continue
        leg_won = [p for p in leg_parlays if p["result"] == "won"]
        leg_staked = sum(p["stake"] for p in leg_parlays)
        leg_profit = sum(p["profit"] for p in leg_parlays)
        by_legs[n] = {
            "total": len(leg_parlays),
            "won": len(leg_won),
            "win_rate": len(leg_won) / len(leg_parlays),
            "staked": round(leg_staked, 2),
            "profit": round(leg_profit, 2),
            "roi": round(leg_profit / leg_staked, 4) if leg_staked > 0 else 0,
        }

    return {
        "total_parlays": len(all_parlays),
        "won": len(won),
        "lost": len(all_parlays) - len(won),
        "win_rate": round(len(won) / len(all_parlays), 4),
        "total_staked": round(total_staked, 2),
        "total_profit": round(total_profit, 2),
        "roi": round(total_profit / total_staked, 4) if total_staked > 0 else 0,
        "by_legs": by_legs,
        "parlays": sorted(all_parlays, key=lambda p: p["date"], reverse=True),
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
