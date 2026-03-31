#!/usr/bin/env python3
"""
Backtest a specific date's games against cached odds.
Runs the full model pipeline, finds +EV bets, checks results,
and adds them to data/bet_results.json.

Usage:
    python backtest_day.py 2026-03-14
    python backtest_day.py 2026-03-14 --dry-run    # Preview without saving
    python backtest_day.py 2026-03-14 --stake 0.50  # Custom stake (default $0.50)
"""

import argparse
import json
import sys
import math
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.data.nhl_data import fetch_season_games, fetch_standings, get_team_recent_form
from src.data.odds_fetcher import (
    parse_odds, get_best_odds, get_consensus_no_vig_odds,
    team_name_to_abbrev, american_to_decimal,
)
from src.data.scraper import get_player_data_nhl_api_only
from src.models.model import find_similar_games, estimate_probabilities, blend_model_and_market
from src.models.ml_model import blend_ml_and_similarity
from src.models.ml_model_streamlined import StreamlinedNHLMLModel
from src.analysis.ev_calculator import evaluate_all_bets, calculate_ev
from src.analysis.goalie_tracker import get_todays_starters
from src.analysis.injury_tracker import calculate_injury_impact
from src.analysis.injury_impact_enhanced import get_injury_adjusted_probabilities
from src.analysis.advanced_stats import get_team_advanced_stats
from src.analysis.team_splits import get_team_splits


CACHE_DIR = Path(__file__).parent / "cache"
BET_RESULTS_PATH = Path(__file__).parent / "data" / "bet_results.json"


def find_cached_odds_for_date(target_date: str) -> list:
    """
    Find cached odds files that contain games for the target date.
    Odds are often fetched the day before, so check both target date
    and the day before.
    """
    import glob

    target = datetime.strptime(target_date, "%Y-%m-%d")
    day_before = target - timedelta(days=1)
    day_of = target
    day_after = target + timedelta(days=1)

    # Look for cached odds files from target day and day before
    candidates = []
    for check_date in [day_before, day_of, day_after]:
        date_str = check_date.strftime("%Y%m%d")
        pattern = str(CACHE_DIR / f"odds_nhl_h2h_spreads_totals_{date_str}_*.json")
        candidates.extend(glob.glob(pattern))

    if not candidates:
        return []

    # Load all cached odds and filter for target date games
    all_games = []
    seen_game_ids = set()

    for cache_file in sorted(candidates):
        try:
            with open(cache_file) as f:
                raw_games = json.load(f)

            for game in raw_games:
                ct = game.get("commence_time", "")
                game_date = ct[:10]

                # Games on target date or early next day UTC (late evening EST)
                next_day = (target + timedelta(days=1)).strftime("%Y-%m-%d")

                if game_date == target_date:
                    game_id = game.get("id", f"{game['away_team']}_{game['home_team']}")
                    if game_id not in seen_game_ids:
                        all_games.append(game)
                        seen_game_ids.add(game_id)
                elif game_date == next_day:
                    # Games starting before 10:00 UTC next day = evening EST target day
                    hour = int(ct[11:13]) if len(ct) > 13 else 0
                    if hour < 10:
                        game_id = game.get("id", f"{game['away_team']}_{game['home_team']}")
                        if game_id not in seen_game_ids:
                            all_games.append(game)
                            seen_game_ids.add(game_id)
        except Exception as e:
            print(f"  Warning: Could not load {cache_file}: {e}")

    return all_games


def get_game_results_for_date(target_date: str, all_games: list) -> dict:
    """Get actual game results for a specific date."""
    results = {}
    for game in all_games:
        date = game["date"][:10]
        if date == target_date:
            home = game["home_team"]
            away = game["away_team"]
            game_key = f"{away} @ {home}"
            results[game_key] = {
                "date": date,
                "home_score": game["home_score"],
                "away_score": game["away_score"],
                "total": game["home_score"] + game["away_score"],
                "home_won": game["home_score"] > game["away_score"],
                "away_won": game["away_score"] > game["home_score"],
            }
    return results


def check_bet_result(bet: dict, result: dict):
    """Check if a bet won based on the actual game result."""
    pick = bet["pick"]
    bet_type = bet["bet_type"]

    if bet_type == "Moneyline":
        team = pick.split(" ")[0]
        game = bet["game"]
        if team in game.split(" @ ")[0]:  # Away team
            return result["away_won"]
        else:
            return result["home_won"]

    elif bet_type == "Total":
        parts = pick.split(" ")
        over_under = parts[0].lower()
        line = float(parts[1])
        if over_under == "over":
            return result["total"] > line
        else:
            return result["total"] < line

    elif bet_type == "Spread":
        return None  # Skip spreads

    return None


def backtest_date(target_date: str, stake: float = 0.50, dry_run: bool = False,
                  min_edge: float = 0.02, conservative: bool = True):
    """
    Run the full model pipeline for a historical date using cached odds.
    """
    print("=" * 70)
    print(f"  BACKFILLING BETS FOR {target_date}")
    print("=" * 70)
    print()

    # Step 1: Find cached odds
    print("[1/6] Looking for cached odds...")
    raw_odds_games = find_cached_odds_for_date(target_date)

    if not raw_odds_games:
        print(f"  ERROR: No cached odds found for {target_date}")
        print(f"  Checked cache dir: {CACHE_DIR}")
        print("  Cannot backfill without historical odds data.")
        return []

    odds_games = parse_odds(raw_odds_games)
    print(f"  Found odds for {len(odds_games)} games")

    # Step 2: Get game results
    print("\n[2/6] Fetching game results...")
    historical_games = fetch_season_games(days_back=14)
    game_results = get_game_results_for_date(target_date, historical_games)
    print(f"  Found results for {len(game_results)} games on {target_date}")

    if not game_results:
        print("  ERROR: No game results found. Games may not have been played yet.")
        return []

    # Step 3: Load model data
    print("\n[3/6] Loading standings and model data...")
    # Use standings from target date for accuracy
    standings = fetch_standings(date=target_date)
    print(f"  Loaded standings for {len(standings)} teams")

    all_games = fetch_season_games(days_back=90)
    # Filter to only games before the target date (no lookahead)
    all_games_before = [g for g in all_games if g["date"][:10] < target_date]
    print(f"  Using {len(all_games_before)} historical games (before {target_date})")

    # Team forms
    team_forms = {}
    for team in standings:
        team_forms[team] = get_team_recent_form(team, all_games_before, n=10)

    # Step 4: Load ML model
    print("\n[4/6] Loading ML model...")
    ml_model = StreamlinedNHLMLModel()
    if not ml_model.load_models():
        print("  Training model...")
        ml_model.train(all_games_before, standings, team_forms)
    else:
        print("  Loaded existing model")

    # Step 5: Run analysis for each game
    print(f"\n[5/6] Running model analysis (conservative={conservative}, min_edge={min_edge:.0%})...")
    print()

    all_bets = []

    for game_data in odds_games:
        home_full = game_data["home_team"]
        away_full = game_data["away_team"]
        home = team_name_to_abbrev(home_full)
        away = team_name_to_abbrev(away_full)

        if home not in standings or away not in standings:
            print(f"  Skipping {away_full} @ {home_full} (team not in standings)")
            continue

        game_label = f"{away} @ {home}"

        if game_label not in game_results:
            print(f"  Skipping {game_label} (no result found)")
            continue

        # Get best odds and market consensus
        best_odds = get_best_odds(game_data)
        market_probs = get_consensus_no_vig_odds(game_data)

        # Find similar games
        similar = find_similar_games(
            home, away, standings, all_games_before, team_forms,
            n_similar=50,
        )

        # Get total/spread lines
        total_line = None
        spread_line = None
        thescore_odds = best_odds.get("all_books", {}).get("thescore", {})
        if thescore_odds.get("total_over"):
            total_line = thescore_odds["total_over"]["point"]
        elif best_odds["total"]["over"]:
            total_line = best_odds["total"]["over"]["point"]

        if thescore_odds.get("spread_home"):
            spread_line = thescore_odds["spread_home"]["point"]
        elif best_odds["spread"]["home"]:
            spread_line = best_odds["spread"]["home"]["point"]

        # Estimate probabilities from similar games
        model_probs = estimate_probabilities(
            similar, home, away,
            total_line=total_line,
            spread_line=spread_line,
        )

        # ML prediction
        game_date = game_data["commence_time"][:10]
        player_data = get_player_data_nhl_api_only(home, away, game_date)

        # Add advanced stats
        player_data['home_advanced_stats'] = get_team_advanced_stats(home)
        player_data['away_advanced_stats'] = get_team_advanced_stats(away)

        # Add splits
        home_splits = get_team_splits(home, all_games_before, n_recent=10)
        away_splits = get_team_splits(away, all_games_before, n_recent=10)
        player_data['home_team_splits'] = home_splits['home_recent']
        player_data['away_team_splits'] = away_splits['road_recent']

        home_stats = {**standings[home], "win_pct": standings[home].get("win_pct", 0.5)}
        away_stats = {**standings[away], "win_pct": standings[away].get("win_pct", 0.5)}

        ml_pred = ml_model.predict_with_context(
            home_stats, away_stats,
            team_forms[home], team_forms[away],
            player_data
        )

        if ml_pred:
            model_probs_enhanced = blend_ml_and_similarity(ml_pred, model_probs, ml_weight=0.48)
            model_probs["home_win_prob"] = model_probs_enhanced["home_win_prob"]
            model_probs["away_win_prob"] = model_probs_enhanced["away_win_prob"]
            model_probs["expected_total"] = model_probs_enhanced["expected_total"]

        # Blend with market
        blended = blend_model_and_market(model_probs, market_probs)

        # Evaluate bets
        game_bets = evaluate_all_bets(
            game_label, home, away,
            blended, best_odds,
            stake=stake, min_edge=min_edge,
            conservative=conservative,
        )

        result = game_results[game_label]
        result_str = f"{result['away_score']}-{result['home_score']} (total {result['total']})"

        if game_bets:
            print(f"  {game_label}: {len(game_bets)} +EV bets | Result: {result_str}")
            for bet in game_bets:
                print(f"    -> {bet['pick']} @ {bet['odds']:+d} ({bet['book']}) "
                      f"edge={bet['edge']:.1%} EV=${bet['ev']:.3f}")
        else:
            print(f"  {game_label}: no +EV bets | Result: {result_str}")

        all_bets.extend(game_bets)

    print(f"\n  Total +EV bets found: {len(all_bets)}")

    if not all_bets:
        print("\n  No +EV bets to add.")
        return []

    # Step 6: Check results and add to bet_results.json
    print(f"\n[6/6] {'[DRY RUN] ' if dry_run else ''}Recording results...")

    # Load existing results
    if BET_RESULTS_PATH.exists():
        results_log = json.loads(BET_RESULTS_PATH.read_text())
    else:
        results_log = {"results": {}}

    added = 0
    skipped = 0

    for bet in all_bets:
        bet_id = f"{bet['game']}_{bet['pick']}"

        # Skip if already exists
        if bet_id in results_log["results"]:
            print(f"  SKIP (exists): {bet_id}")
            skipped += 1
            continue

        game_key = bet["game"]
        if game_key not in game_results:
            print(f"  SKIP (no result): {bet_id}")
            skipped += 1
            continue

        result = game_results[game_key]
        won = check_bet_result(bet, result)

        if won is None:
            print(f"  SKIP (can't determine): {bet_id}")
            skipped += 1
            continue

        # Calculate profit
        if won:
            decimal_odds = american_to_decimal(bet["odds"])
            profit = stake * (decimal_odds - 1)
        else:
            profit = -stake

        # Build bet record (matching existing format)
        bet_record = {
            "game": bet["game"],
            "bet_type": bet["bet_type"],
            "pick": bet["pick"],
            "book": bet["book"],
            "odds": bet["odds"],
            "ev": bet["ev"],
            "roi": bet["roi"],
            "edge": bet["edge"],
            "true_prob": bet["true_prob"],
            "implied_prob": bet["implied_prob"],
            "american_odds": bet["american_odds"],
            "decimal_odds": bet["decimal_odds"],
            "stake": stake,
            "profit_if_win": stake * (american_to_decimal(bet["odds"]) - 1),
            "loss_if_lose": stake,
            "is_positive_ev": True,
            "confidence": bet.get("confidence", 0),
            "analysis_timestamp": f"{target_date}T12:00:00.000000",
        }

        entry = {
            "bet": bet_record,
            "result": "won" if won else "lost",
            "profit": profit,
            "game_result": result,
            "checked_at": datetime.now().isoformat(),
        }

        result_icon = "WON" if won else "LOST"
        print(f"  {result_icon}: {bet_id} -> ${profit:+.3f}")

        if not dry_run:
            results_log["results"][bet_id] = entry
        added += 1

    if not dry_run and added > 0:
        BET_RESULTS_PATH.write_text(json.dumps(results_log, indent=2, default=str))
        print(f"\n  Saved {added} new bets to {BET_RESULTS_PATH}")
    elif dry_run:
        print(f"\n  [DRY RUN] Would add {added} bets (skipped {skipped})")
    else:
        print(f"\n  No new bets to add (skipped {skipped})")

    # Print summary
    if added > 0:
        won_count = sum(1 for b in all_bets
                       if check_bet_result(b, game_results.get(b["game"], {})) == True)
        lost_count = added - won_count
        total_profit = sum(
            stake * (american_to_decimal(b["odds"]) - 1)
            if check_bet_result(b, game_results.get(b["game"], {})) else -stake
            for b in all_bets
            if check_bet_result(b, game_results.get(b["game"], {})) is not None
        )

        print(f"\n  Summary for {target_date}:")
        print(f"    Bets: {added} | Won: {won_count} | Lost: {lost_count}")
        print(f"    Win rate: {won_count/added*100:.0f}%")
        print(f"    Profit: ${total_profit:+.3f}")

    return all_bets


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill bets for a specific date")
    parser.add_argument("date", help="Date to backfill (YYYY-MM-DD)")
    parser.add_argument("--stake", type=float, default=0.50, help="Stake per bet (default: $0.50)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    parser.add_argument("--min-edge", type=float, default=0.02, help="Min edge (default: 0.02)")
    parser.add_argument("--aggressive", action="store_true",
                       help="Include spreads (default: conservative/ML+totals only)")
    args = parser.parse_args()

    # Validate date format
    try:
        datetime.strptime(args.date, "%Y-%m-%d")
    except ValueError:
        print(f"ERROR: Invalid date format '{args.date}'. Use YYYY-MM-DD.")
        sys.exit(1)

    backtest_date(
        target_date=args.date,
        stake=args.stake,
        dry_run=args.dry_run,
        min_edge=args.min_edge,
        conservative=not args.aggressive,
    )
