#!/usr/bin/env python3
"""
MLB +EV Betting Finder
======================
Compares live MLB betting lines to model predictions
to find positive expected value bets.

Usage:
    python main.py                   # Full analysis with live odds
    python main.py --no-odds         # Historical analysis only
    python main.py --stake 0.50      # Set stake per bet (default $0.50)
    python main.py --days 90         # Historical lookback days
    python main.py --min-edge 0.03   # Minimum edge threshold (default 3%)
"""

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.data import (
    fetch_standings,
    fetch_season_games,
    fetch_todays_games,
    get_team_recent_form,
    get_h2h_record,
    get_pitcher_stats,
    get_bullpen_stats,
    get_park_factors,
    fetch_mlb_odds,
    parse_odds,
    get_best_odds,
    get_consensus_no_vig_odds,
    team_name_to_abbrev,
)
from src.data.mlb_data import get_team_splits, get_team_batting_splits, get_rest_days
from src.models import (
    find_similar_games,
    estimate_probabilities,
    blend_model_and_market,
    MLBMLModel,
    blend_ml_and_similarity,
)
from src.analysis import (
    evaluate_all_bets,
    format_recommendations,
    kelly_criterion,
    calculate_ev,
    get_performance_stats,
    save_analysis,
    get_history_stats,
)


def run_analysis(
    stake=0.50,
    days_back=90,
    min_edge=0.03,
    use_odds=True,
    n_similar=50,
    conservative=True,
    book_filter="soft",
):
    """Main analysis pipeline."""
    print("=" * 60)
    print("  MLB +EV Betting Finder")
    if conservative:
        print("  MODE: Conservative (moneylines + totals only, 3%+ edge)")
    print(f"  {datetime.now().strftime('%A, %B %d %Y %H:%M')}")
    print("=" * 60)
    print()

    # Step 1: Fetch standings
    print("[1/5] Fetching current MLB standings...")
    standings = fetch_standings()
    print(f"  Loaded standings for {len(standings)} teams")

    # Step 2: Fetch historical games
    print(f"\n[2/5] Fetching last {days_back} days of game results...")
    all_games = fetch_season_games(days_back=days_back)
    print(f"  Loaded {len(all_games)} completed games")

    # Step 3: Calculate recent form
    print("\n[3/5] Calculating team form...")
    team_forms = {}
    for team in standings:
        team_forms[team] = get_team_recent_form(team, all_games, n=10)

    # Step 3.5: Train/load ML model
    print(f"\n[3.5/5] Initializing ML model ({len(MLBMLModel.FEATURE_NAMES)} features)...")
    ml_model = MLBMLModel()

    model_path = Path(__file__).parent / "ml_models" / "win_model.pkl"
    should_retrain = False

    if model_path.exists():
        age_days = (time.time() - model_path.stat().st_mtime) / 86400
        print(f"  Found existing models (age: {age_days:.1f} days)")
        if age_days > 1:
            print(f"  Models are stale, retraining...")
            should_retrain = True
        else:
            try:
                ml_model.load_models()
                n_features = ml_model.model_win.n_features_in_
                expected = len(MLBMLModel.FEATURE_NAMES)
                if n_features != expected:
                    print(f"  Model has {n_features} features, need {expected}. Retraining...")
                    should_retrain = True
                else:
                    print(f"  Models fresh ({n_features} features), loaded from disk")
            except Exception:
                should_retrain = True
    else:
        print("  No existing models, training new ones...")
        should_retrain = True

    # Pre-compute bullpen stats for all teams (needed for training and prediction)
    print("\n  Pre-computing bullpen stats...")
    bullpen_cache = {}
    for team in standings:
        bullpen_cache[team] = get_bullpen_stats(team, all_games)

    if should_retrain:
        print("  Training ML model...")
        ml_model.train(all_games, standings, team_forms,
                       pitcher_cache=None, bullpen_cache=bullpen_cache)

    if not ml_model.is_trained:
        try:
            ml_model.load_models()
        except Exception:
            print("  ML model unavailable, using similarity-only")

    # Step 4: Fetch odds
    odds_games = []
    quota_info = None
    if use_odds:
        print("\n[4/5] Fetching live betting odds...")
        try:
            raw_odds, quota_info = fetch_mlb_odds()
            odds_games = parse_odds(raw_odds)

            # Filter to pre-game only
            now_utc = datetime.now(timezone.utc)
            pre_game_only = []
            for g in odds_games:
                game_time = datetime.fromisoformat(g["commence_time"].replace('Z', '+00:00'))
                hours_until = (game_time - now_utc).total_seconds() / 3600
                if hours_until > 0.5:
                    pre_game_only.append(g)
                else:
                    print(f"  Skipping {g['away_team']} @ {g['home_team']} (game started)")
            odds_games = pre_game_only

            # Filter to today's games only
            today = datetime.now()
            today_str = today.strftime("%Y-%m-%d")
            tomorrow_str = (today + timedelta(days=1)).strftime("%Y-%m-%d")
            filtered = []
            for g in odds_games:
                ct = g["commence_time"]
                if ct[:10] == today_str:
                    filtered.append(g)
                elif ct[:10] == tomorrow_str:
                    hour = int(ct[11:13]) if len(ct) > 13 else 0
                    if hour < 10:  # Late EST games show as tomorrow UTC
                        filtered.append(g)
            odds_games = filtered

            print(f"  Found odds for {len(odds_games)} games today")
        except Exception as e:
            print(f"  Warning: Could not fetch odds: {e}")
            use_odds = False

    # Step 5: Analyze games
    print("\n[5/5] Running model analysis...\n")
    print("-" * 60)

    all_bets = []
    game_analyses = []

    if use_odds and odds_games:
        # Pre-compute team data
        unique_teams = set()
        for game_data in odds_games:
            h = team_name_to_abbrev(game_data["home_team"])
            a = team_name_to_abbrev(game_data["away_team"])
            if h in standings:
                unique_teams.add(h)
            if a in standings:
                unique_teams.add(a)

        print(f"  Pre-computing splits & context for {len(unique_teams)} teams...")
        team_splits_cache = {}
        team_batting_splits_cache = {}
        for team in unique_teams:
            team_splits_cache[team] = get_team_splits(team, all_games, n_recent=10)
            team_batting_splits_cache[team] = get_team_batting_splits(team)

        # Analyze each game
        for game_data in odds_games:
            home_full = game_data["home_team"]
            away_full = game_data["away_team"]
            home = team_name_to_abbrev(home_full)
            away = team_name_to_abbrev(away_full)

            if home not in standings or away not in standings:
                print(f"  Skipping {away_full} @ {home_full} (team not in standings)")
                continue

            game_label = f"{away} @ {home}"
            print(f"\n  Analyzing: {game_label}")

            best_odds = get_best_odds(game_data)
            market_probs = get_consensus_no_vig_odds(game_data)

            # Find similar games
            similar = find_similar_games(home, away, standings, all_games, team_forms,
                                        n_similar=n_similar)
            print(f"    Found {len(similar)} similar historical games")

            # Get total/spread lines
            total_line = None
            spread_line = None
            if best_odds["total"]["over"]:
                total_line = best_odds["total"]["over"]["point"]
            if best_odds["spread"]["home"]:
                spread_line = best_odds["spread"]["home"]["point"]

            # Estimate probabilities from similar games
            model_probs = estimate_probabilities(similar, home, away,
                                                 total_line=total_line,
                                                 spread_line=spread_line)

            # Get pitcher stats for today's starters
            today_games = fetch_todays_games()
            home_pitcher = {}
            away_pitcher = {}
            home_pitcher_name = "TBD"
            away_pitcher_name = "TBD"

            for tg in today_games:
                if tg["home_team"] == home and tg["away_team"] == away:
                    home_pitcher = get_pitcher_stats(tg.get("home_pitcher_id"))
                    away_pitcher = get_pitcher_stats(tg.get("away_pitcher_id"))
                    home_pitcher_name = tg.get("home_pitcher_name", "TBD")
                    away_pitcher_name = tg.get("away_pitcher_name", "TBD")
                    break

            # Build context for ML model
            game_date = game_data["commence_time"][:10]
            home_splits = team_splits_cache.get(home, {"home_recent": {}, "road_recent": {}})
            away_splits = team_splits_cache.get(away, {"home_recent": {}, "road_recent": {}})
            home_bat_splits = team_batting_splits_cache.get(home, {"vs_lhp": {}, "vs_rhp": {}})
            away_bat_splits = team_batting_splits_cache.get(away, {"vs_lhp": {}, "vs_rhp": {}})

            # L/R matchup: home team batting vs away pitcher hand, and vice versa
            away_hand = away_pitcher.get("handedness", "R")
            home_hand = home_pitcher.get("handedness", "R")
            home_vs_key = "vs_lhp" if away_hand == "L" else "vs_rhp"
            away_vs_key = "vs_lhp" if home_hand == "L" else "vs_rhp"

            context = {
                "park_factor": get_park_factors(home),
                "home_rest_days": get_rest_days(home, game_date, all_games),
                "away_rest_days": get_rest_days(away, game_date, all_games),
                "is_night": 1.0,  # Default — most games are night
                "home_bullpen_era": bullpen_cache.get(home, {}).get("bullpen_era", 4.00),
                "home_bullpen_quality": bullpen_cache.get(home, {}).get("bullpen_quality", 50),
                "away_bullpen_era": bullpen_cache.get(away, {}).get("bullpen_era", 4.00),
                "away_bullpen_quality": bullpen_cache.get(away, {}).get("bullpen_quality", 50),
                "home_split_rs": home_splits.get("home_recent", {}).get("rs_pg", 4.5),
                "home_split_ra": home_splits.get("home_recent", {}).get("ra_pg", 4.5),
                "away_road_split_rs": away_splits.get("road_recent", {}).get("rs_pg", 4.5),
                "away_road_split_ra": away_splits.get("road_recent", {}).get("ra_pg", 4.5),
                "home_bat_vs_opp_hand_ops": home_bat_splits.get(home_vs_key, {}).get("ops", 0.725),
                "away_bat_vs_opp_hand_ops": away_bat_splits.get(away_vs_key, {}).get("ops", 0.725),
                "home_streak": 0,
                "away_streak": 0,
                "home_form_trend": 0.0,
                "away_form_trend": 0.0,
            }

            # ML prediction
            ml_pred = ml_model.predict(
                standings[home], standings[away],
                team_forms[home], team_forms[away],
                home_pitcher, away_pitcher, context,
            )

            if ml_pred:
                model_probs_enhanced = blend_ml_and_similarity(ml_pred, model_probs, ml_weight=0.45)
                model_probs["home_win_prob"] = model_probs_enhanced["home_win_prob"]
                model_probs["away_win_prob"] = model_probs_enhanced["away_win_prob"]
                model_probs["expected_total"] = model_probs_enhanced["expected_total"]

            # Blend with market
            blended = blend_model_and_market(model_probs, market_probs)

            # Print analysis
            ml_tag = " (ML+Pitcher)" if ml_pred else ""
            print(f"    Model{ml_tag}: {home} {model_probs['home_win_prob']:.1%} / "
                  f"{away} {model_probs['away_win_prob']:.1%} "
                  f"(confidence: {model_probs['confidence']:.0%})")
            print(f"    Market: {home} {market_probs['home_win_prob']:.1%} / "
                  f"{away} {market_probs['away_win_prob']:.1%}")
            print(f"    Blended: {home} {blended['home_win_prob']:.1%} / "
                  f"{away} {blended['away_win_prob']:.1%}")
            if total_line:
                print(f"    Total: line {total_line}, model expects "
                      f"{model_probs['expected_total']:.1f} runs "
                      f"(O {blended['over_prob']:.1%} / U {blended['under_prob']:.1%})")
            print(f"    Pitchers: {away_pitcher_name} vs {home_pitcher_name}")

            # Find +EV bets
            game_bets = evaluate_all_bets(
                game_label, home, away,
                blended, best_odds,
                stake=stake, min_edge=min_edge,
                conservative=conservative,
                book_filter=book_filter,
            )

            # Attach line shopping data
            all_books = best_odds.get("all_books", {})
            for bet in game_bets:
                bet_type = bet.get("bet_type", "")
                pick = bet.get("pick", "")
                book_odds_list = []
                for bk, bk_odds in all_books.items():
                    if bet_type == "Moneyline":
                        side = "home" if home in pick else "away"
                        key = f"ml_{side}"
                        if key in bk_odds:
                            book_odds_list.append({"book": bk, "odds": bk_odds[key]})
                    elif bet_type == "Total":
                        side = "over" if "Over" in pick else "under"
                        key = f"total_{side}"
                        if key in bk_odds:
                            book_odds_list.append({
                                "book": bk,
                                "odds": bk_odds[key]["price"],
                                "point": bk_odds[key]["point"],
                            })
                book_odds_list.sort(key=lambda x: x["odds"], reverse=True)
                bet["all_book_odds"] = book_odds_list

            if game_bets:
                print(f"    >>> Found {len(game_bets)} +EV bets!")
            else:
                print(f"    No +EV bets at current lines")

            all_bets.extend(game_bets)

            # Build context indicators for UI
            context_indicators = {
                "fatigue": [], "pitcher": [], "splits": [], "park": [],
            }

            if context["home_rest_days"] == 1:
                context_indicators["fatigue"].append({"team": home, "type": "B2B", "severity": "medium"})
            if context["away_rest_days"] == 1:
                context_indicators["fatigue"].append({"team": away, "type": "B2B", "severity": "medium"})
            if context["home_rest_days"] >= 3:
                context_indicators["fatigue"].append({"team": home, "type": "well-rested", "severity": "positive"})
            if context["away_rest_days"] >= 3:
                context_indicators["fatigue"].append({"team": away, "type": "well-rested", "severity": "positive"})

            # Pitcher indicators
            if home_pitcher.get("quality_score", 50) >= 70:
                context_indicators["pitcher"].append({"team": home, "type": "ace", "value": home_pitcher["quality_score"], "severity": "positive"})
            elif home_pitcher.get("quality_score", 50) <= 35:
                context_indicators["pitcher"].append({"team": home, "type": "weak", "value": home_pitcher.get("quality_score", 50), "severity": "negative"})

            if away_pitcher.get("quality_score", 50) >= 70:
                context_indicators["pitcher"].append({"team": away, "type": "ace", "value": away_pitcher["quality_score"], "severity": "positive"})
            elif away_pitcher.get("quality_score", 50) <= 35:
                context_indicators["pitcher"].append({"team": away, "type": "weak", "value": away_pitcher.get("quality_score", 50), "severity": "negative"})

            # Park factor
            pf = get_park_factors(home)
            if pf >= 105:
                context_indicators["park"].append({"team": home, "type": "hitter-friendly", "value": pf, "severity": "medium"})
            elif pf <= 96:
                context_indicators["park"].append({"team": home, "type": "pitcher-friendly", "value": pf, "severity": "medium"})

            game_analyses.append({
                "game": game_label,
                "home": home,
                "away": away,
                "model_probs": model_probs,
                "market_probs": market_probs,
                "blended_probs": blended,
                "n_similar": len(similar),
                "n_bets": len(game_bets),
                "context_indicators": context_indicators,
                "pitcher_matchup": {
                    "home": {
                        "name": home_pitcher_name,
                        "era": home_pitcher.get("era", 4.50),
                        "whip": home_pitcher.get("whip", 1.30),
                        "k_per_9": home_pitcher.get("k_per_9", 8.0),
                        "fip": home_pitcher.get("fip", 4.30),
                        "quality_score": home_pitcher.get("quality_score", 50),
                        "handedness": home_pitcher.get("handedness", "R"),
                    },
                    "away": {
                        "name": away_pitcher_name,
                        "era": away_pitcher.get("era", 4.50),
                        "whip": away_pitcher.get("whip", 1.30),
                        "k_per_9": away_pitcher.get("k_per_9", 8.0),
                        "fip": away_pitcher.get("fip", 4.30),
                        "quality_score": away_pitcher.get("quality_score", 50),
                        "handedness": away_pitcher.get("handedness", "R"),
                    },
                },
                "team_splits": {
                    "home": home_splits.get("home_recent", {}),
                    "away": away_splits.get("road_recent", {}),
                },
                "bullpen": {
                    "home": bullpen_cache.get(home, {}),
                    "away": bullpen_cache.get(away, {}),
                },
                "park_factor": get_park_factors(home),
            })

    else:
        print("  Running in historical-only mode")
        todays = fetch_todays_games()
        if not todays:
            print("  No games scheduled today.")

        for game in todays:
            home = game["home_team"]
            away = game["away_team"]
            game_label = f"{away} @ {home}"
            if home not in standings or away not in standings:
                continue

            print(f"\n  Analyzing: {game_label}")
            similar = find_similar_games(home, away, standings, all_games, team_forms,
                                        n_similar=n_similar)
            model_probs = estimate_probabilities(similar, home, away)

            print(f"    Model: {home} {model_probs['home_win_prob']:.1%} / "
                  f"{away} {model_probs['away_win_prob']:.1%}")
            print(f"    Expected total: {model_probs['expected_total']:.1f} runs")
            print(f"    Confidence: {model_probs['confidence']:.0%}")

            game_analyses.append({
                "game": game_label, "home": home, "away": away,
                "model_probs": model_probs,
            })

    # Print recommendations
    print("\n")
    report = format_recommendations(all_bets, top_n=15, quota_info=quota_info)
    print(report)

    # Show past performance
    stats = get_performance_stats()
    if stats:
        print("\n" + "=" * 75)
        print("  PAST PERFORMANCE (Tracked Bets)")
        print("=" * 75)
        print(f"  Total bets: {stats['total_bets']} | "
              f"Won: {stats['won']} ({stats['win_rate']:.1%}) | "
              f"Lost: {stats['lost']}")
        print(f"  Total staked: ${stats['total_staked']:.2f} | "
              f"Profit: ${stats['total_profit']:+.2f} | "
              f"ROI: {stats['roi']:+.2%}")
        if stats.get('by_grade'):
            print("\n  By Grade:")
            for grade in ["A", "B+", "B", "C+"]:
                if grade in stats['by_grade']:
                    g = stats['by_grade'][grade]
                    wr = g['won'] / len(g['bets']) if g['bets'] else 0
                    roi = g['profit'] / g['staked'] if g['staked'] > 0 else 0
                    print(f"    [{grade:3s}] {len(g['bets']):2d} bets | "
                          f"Win: {wr:.1%} | ROI: {roi:+.1%}")
        print("=" * 75)

    # Save results
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stake": stake,
        "days_back": days_back,
        "min_edge": min_edge,
        "n_historical_games": len(all_games),
        "games_analyzed": game_analyses,
        "recommendations": [
            {k: v for k, v in bet.items() if not callable(v)}
            for bet in all_bets
        ],
        "quota_info": quota_info,
    }

    output_path = Path(__file__).parent / "mlbdata" / "latest_analysis.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"Full analysis saved to: {output_path}")

    save_analysis(output)

    hist_stats = get_history_stats(days_back=7)
    if hist_stats:
        print(f"  History: {hist_stats['total_analyses']} analyses, "
              f"{hist_stats['total_bets_recommended']} bets in last 7 days")

    return all_bets, game_analyses


def main():
    parser = argparse.ArgumentParser(description="MLB +EV Betting Finder")
    parser.add_argument("--stake", type=float, default=0.50,
                        help="Stake per bet (default: $0.50)")
    parser.add_argument("--days", type=int, default=90,
                        help="Historical lookback days (default: 90)")
    parser.add_argument("--min-edge", type=float, default=0.03,
                        help="Minimum edge to recommend (default: 0.03 = 3%%)")
    parser.add_argument("--no-odds", action="store_true",
                        help="Run without live odds")
    parser.add_argument("--similar", type=int, default=50,
                        help="Number of similar games (default: 50)")
    parser.add_argument("--conservative", action="store_true", default=True,
                        help="Conservative mode: ML + totals only, 3%+ edge")
    parser.add_argument("--with-runlines", action="store_true",
                        help="Include run line bets")
    parser.add_argument("--all-books", action="store_true",
                        help="Include sharp books")
    args = parser.parse_args()

    run_analysis(
        stake=args.stake,
        days_back=args.days,
        min_edge=args.min_edge,
        use_odds=not args.no_odds,
        n_similar=args.similar,
        conservative=not args.with_runlines,
        book_filter="all" if args.all_books else "soft",
    )


if __name__ == "__main__":
    main()
