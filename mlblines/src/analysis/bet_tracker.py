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


def get_parlay_performance(stake: float = 0.50):
    """
    Reconstruct parlay performance from historical straight bet results.

    Groups resolved ML + Over bets by date, forms 2-3 leg parlay combos,
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

    # Group resolved parlay-eligible bets by date.
    # Matches the post-fix generate_parlays() filters:
    #   - ML legs: <+130 odds AND edge >= 5% (raised because MLB ML WR is 33%)
    #   - Over legs: edge >= 3%
    by_date = defaultdict(list)
    for bet_id, r in results.items():
        if r["result"] == "push":
            continue
        bet = r["bet"]
        edge = bet.get("edge", 0)
        bt = bet.get("bet_type", "")
        odds = bet.get("odds", 0)
        pick = bet.get("pick", "")

        is_ml = bt == "Moneyline" and odds < 130 and edge >= 0.05
        is_over = bt == "Total" and "Over" in pick and edge >= 0.03
        if not (is_ml or is_over):
            continue

        # Extract date
        ts = bet.get("analysis_timestamp", "")
        date = ts[:10] if ts else bet_id[:10]
        if not date or len(date) < 10:
            continue

        by_date[date].append(r)

    # Build parlays for each date that had 2+ qualifying bets.
    # Cap to top 3 per day by EV — matches post-fix generate_parlays() output
    # and reflects the 2-leg-only restriction (no 3-leg combos generated here).
    TOP_N_PER_DAY = 3
    all_parlays = []
    for date in sorted(by_date.keys()):
        day_bets = by_date[date]
        if len(day_bets) < 2:
            continue

        # Get a representative timestamp for this date from the bets
        day_timestamps = [
            r["bet"].get("analysis_timestamp", "")
            for r in day_bets if r["bet"].get("analysis_timestamp")
        ]
        day_datetime = day_timestamps[0] if day_timestamps else f"{date}T12:00:00"

        day_parlays = []
        # 2-leg only — 3-leg MLB parlays went 6W/115L (5% WR) historically.
        for n_legs in range(2, min(3, len(day_bets) + 1)):
            for combo in combinations(day_bets, n_legs):
                # No same-game parlays: correlated MLB outcomes inflate
                # the independent-legs parlay EV calculation.
                seen_games = set()
                skip = False
                for r in combo:
                    if r["bet"]["game"] in seen_games:
                        skip = True
                        break
                    seen_games.add(r["bet"]["game"])
                if skip:
                    continue

                # Check if all legs hit
                all_won = all(r["result"] == "won" for r in combo)

                # Calculate combined odds and EV
                combined_decimal = 1.0
                combined_true_prob = 1.0
                combined_implied_prob = 1.0
                for r in combo:
                    combined_decimal *= american_to_decimal(r["bet"]["odds"])
                    combined_true_prob *= r["bet"].get("true_prob", 0.5)
                    combined_implied_prob *= r["bet"].get("implied_prob", 0.5)

                payout = stake * (combined_decimal - 1)
                ev = (combined_true_prob * payout) - ((1 - combined_true_prob) * stake)

                if all_won:
                    profit = payout
                    result = "won"
                else:
                    profit = -stake
                    result = "lost"

                # Combined American odds
                if combined_decimal >= 2.0:
                    combined_american = int(round((combined_decimal - 1) * 100))
                else:
                    combined_american = int(round(-100 / (combined_decimal - 1)))

                day_parlays.append({
                    "date": date,
                    "datetime": day_datetime,
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
                    "combined_true_prob": round(combined_true_prob, 4),
                    "combined_implied_prob": round(combined_implied_prob, 4),
                    "ev": round(ev, 4),
                    "payout": round(stake * combined_decimal, 2),
                    "result": result,
                    "profit": round(profit, 2),
                    "stake": stake,
                })

        # Keep only top N per day by EV (matches generate_parlays behavior)
        day_parlays.sort(key=lambda p: p["ev"], reverse=True)
        all_parlays.extend(day_parlays[:TOP_N_PER_DAY])

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
    parser = argparse.ArgumentParser(description="MLB Bet Tracker")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()

    if args.check:
        check_results(days_back=args.days)
    else:
        print("Use --check to check past bet results")
