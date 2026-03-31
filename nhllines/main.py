#!/usr/bin/env python3
"""
NHL +EV Betting Finder
======================
Compares live NHL betting lines to historical similar-game analysis
to find positive expected value bets.

Usage:
    python main.py                   # Full analysis with live odds
    python main.py --no-odds         # Historical analysis only (no API key needed)
    python main.py --stake 0.50      # Set stake per bet (default $1.00 CAD)
    python main.py --days 120        # Historical lookback days (default 90)
    python main.py --min-edge 0.03   # Minimum edge to show (default 0.02)

Setup:
    1. pip3 install requests
    2. Sign up for free API key at https://the-odds-api.com
    3. Create config.json: {"odds_api_key": "YOUR_KEY_HERE"}
       OR set environment variable: export ODDS_API_KEY=your_key
"""

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

# EST = UTC-4 (simple fixed offset, close enough for display purposes)
EST = timezone(timedelta(hours=-4))
from pathlib import Path

from src.data import (
    fetch_standings,
    fetch_season_games,
    fetch_todays_games,
    get_team_recent_form,
    get_h2h_record,
    fetch_nhl_odds,
    parse_odds,
    get_best_odds,
    get_consensus_no_vig_odds,
    team_name_to_abbrev,
    get_player_data_nhl_api_only,
)
from src.models import (
    find_similar_games,
    estimate_probabilities,
    blend_model_and_market,
    StreamlinedNHLMLModel,
)
from src.models.ml_model import NHLMLModel, blend_ml_and_similarity
from src.analysis import (
    evaluate_all_bets,
    format_recommendations,
    kelly_criterion,
    calculate_ev,
    get_performance_stats,
    save_analysis,
    get_history_stats,
    get_todays_starters,
    get_goalie_matchup_analysis,
    get_todays_injuries,
    get_injury_impact_for_game,
    get_team_advanced_stats,
    get_team_splits,
)


def run_analysis(
    stake: float = 1.00,
    days_back: int = 90,
    min_edge: float = 0.02,
    use_odds: bool = True,
    n_similar: int = 50,
    conservative: bool = False,
    book_filter: str = "soft",
):
    """Main analysis pipeline."""
    print("=" * 60)
    print("  NHL +EV Betting Finder")
    if conservative:
        print("  MODE: Conservative (moneylines + totals only, 3%+ edge)")
    print(f"  {datetime.now(EST).strftime('%A, %B %d %Y %H:%M')} EST")
    print("=" * 60)
    print()

    # Step 1: Fetch current standings
    print("[1/5] Fetching current NHL standings...")
    standings = fetch_standings()
    print(f"  Loaded standings for {len(standings)} teams")

    # Step 2: Fetch historical games
    print(f"\n[2/5] Fetching last {days_back} days of game results...")
    all_games = fetch_season_games(days_back=days_back)
    print(f"  Loaded {len(all_games)} completed games")

    # Step 3: Calculate recent form for all teams
    print("\n[3/5] Calculating team form...")
    team_forms = {}
    for team in standings:
        team_forms[team] = get_team_recent_form(team, all_games, n=10)
    
    # Step 3.5: Train/load ML model
    print("\n[3.5/5] Initializing enhanced ML model (52 features: base + contextual + advanced)...")
    ml_model = StreamlinedNHLMLModel()

    # Check if models exist and their age
    model_path = Path(__file__).parent / "ml_models" / "win_model.pkl"
    should_retrain = False

    if model_path.exists():
        import time
        age_days = (time.time() - model_path.stat().st_mtime) / 86400
        print(f"  Found existing models (age: {age_days:.1f} days)")

        # Retrain daily — stale models miss form changes, injuries, roster moves
        if age_days > 1:
            print(f"  ⚠️  Models are stale (>{age_days:.1f} days old), retraining with latest data...")
            should_retrain = True
        else:
            # Try loading and check feature count matches (30 features expected)
            try:
                ml_model.load_models()
                # Verify model expects 30 features
                n_features = ml_model.model_win.n_features_in_
                if n_features != 30:
                    print(f"  ⚠️  Model has {n_features} features, need 30. Retraining...")
                    should_retrain = True
                else:
                    print(f"  ✅ Models are fresh ({n_features} features), loaded from disk")
            except Exception:
                print("  ⚠️  Could not load models, retraining...")
                should_retrain = True
    else:
        print("  No existing models found, training new ones...")
        should_retrain = True

    # Run ML training, goalie fetch, and injury fetch in parallel
    # These are independent operations that together take ~8-10s sequentially
    goalie_starters = {}
    all_injuries = {}

    def _train_model():
        if should_retrain:
            print("  Training enhanced ML model with contextual features...")
            ml_model.train(all_games, standings, team_forms)
        if not ml_model.is_trained:
            try:
                ml_model.load_models()
            except Exception:
                print("  ⚠️  ML model unavailable, falling back to similarity-only")

    def _fetch_goalies():
        print("\n[3.6/5] Fetching goalie data...")
        result = get_todays_starters()
        print(f"  Loaded goalie data for {len(result)} teams")
        return result

    def _fetch_injuries():
        print("\n[3.7/5] Fetching injury data...")
        result = get_todays_injuries()
        print(f"  Loaded injury data for {len(result)} teams")
        return result

    with ThreadPoolExecutor(max_workers=3) as executor:
        model_future = executor.submit(_train_model)
        goalie_future = executor.submit(_fetch_goalies)
        injury_future = executor.submit(_fetch_injuries)

        goalie_starters = goalie_future.result()
        all_injuries = injury_future.result()
        model_future.result()  # Wait for training to complete

    # Step 4: Fetch odds (if enabled)
    odds_games = []
    quota_info = None
    if use_odds:
        print("\n[4/5] Fetching live betting odds...")
        try:
            raw_odds, quota_info = fetch_nhl_odds()
            odds_games = parse_odds(raw_odds)
            
            # Filter out live/finished games
            now_utc = datetime.now(timezone.utc)
            
            pre_game_only = []
            for g in odds_games:
                commence_time_str = g["commence_time"]
                # Parse UTC time
                game_time = datetime.fromisoformat(commence_time_str.replace('Z', '+00:00'))
                hours_until_game = (game_time - now_utc).total_seconds() / 3600
                
                # Only include games that haven't started yet (at least 30 min before)
                if hours_until_game > 0.5:
                    pre_game_only.append(g)
                else:
                    print(f"  Skipping {g['away_team']} @ {g['home_team']} (game started {-hours_until_game:.1f}h ago)")
            
            odds_games = pre_game_only
            
            # Filter to today's games only (commence_time is UTC, we're EST/UTC-5)
            # Include today and tomorrow UTC to catch evening EST games
            today = datetime.now()
            today_str = today.strftime("%Y-%m-%d")
            tomorrow_str = (today + timedelta(days=1)).strftime("%Y-%m-%d")
            odds_games = [
                g for g in odds_games
                if g["commence_time"][:10] in (today_str, tomorrow_str)
            ]
            # Remove games that are clearly tomorrow EST (UTC afternoon+)
            # Games starting after ~10am UTC tomorrow are tomorrow's games EST
            filtered = []
            for g in odds_games:
                ct = g["commence_time"]
                if ct[:10] == today_str:
                    filtered.append(g)
                elif ct[:10] == tomorrow_str:
                    # Tomorrow UTC but before 10:00 UTC = tonight EST
                    hour = int(ct[11:13]) if len(ct) > 13 else 0
                    if hour < 10:
                        filtered.append(g)
            odds_games = filtered
            print(f"  Found odds for {len(odds_games)} games today (pre-game only)")
        except Exception as e:
            print(f"  Warning: Could not fetch odds: {e}")
            print("  Continuing with historical analysis only...")
            use_odds = False

    # Step 5: Run the model
    print("\n[5/5] Running model analysis...\n")
    print("-" * 60)

    all_bets = []
    game_analyses = []

    if use_odds and odds_games:
        # Pre-compute team data for all unique teams (avoids redundant per-game fetches)
        unique_teams = set()
        for game_data in odds_games:
            h = team_name_to_abbrev(game_data["home_team"])
            a = team_name_to_abbrev(game_data["away_team"])
            if h in standings:
                unique_teams.add(h)
            if a in standings:
                unique_teams.add(a)

        print(f"  Pre-computing splits, advanced stats & streaks for {len(unique_teams)} teams...")
        team_splits_cache = {}
        team_advanced_cache = {}
        for team in unique_teams:
            team_splits_cache[team] = get_team_splits(team, all_games, n_recent=10)
            team_advanced_cache[team] = get_team_advanced_stats(team)

        # Pre-compute special teams stats
        team_special_teams_cache = {}
        try:
            from src.analysis.advanced_stats import get_special_teams_stats
            for team in unique_teams:
                team_special_teams_cache[team] = get_special_teams_stats(team)
        except Exception as e:
            print(f"  Warning: Could not load special teams: {e}")

        # Calculate streak momentum for all teams
        team_streaks = StreamlinedNHLMLModel._calculate_streaks(all_games)

        # Get current streak for each team (most recent date)
        today = datetime.now().strftime("%Y-%m-%d")
        team_current_streak = {}
        for team in unique_teams:
            # Find the most recent streak value for this team
            team_dates = sorted([d for (t, d) in team_streaks if t == team], reverse=True)
            if team_dates:
                team_current_streak[team] = team_streaks.get((team, team_dates[0]), 0)
            else:
                team_current_streak[team] = 0

        # Pre-compute H2H records and form trends
        h2h_records = StreamlinedNHLMLModel._calculate_h2h(all_games)
        form_trends = StreamlinedNHLMLModel._calculate_form_trends(all_games)

        # Analyze games with live odds
        for game_data in odds_games:
            home_full = game_data["home_team"]
            away_full = game_data["away_team"]
            home = team_name_to_abbrev(home_full)
            away = team_name_to_abbrev(away_full)

            if home not in standings or away not in standings:
                print(f"  Skipping {away_full} @ {home_full} (team not found in standings)")
                continue

            game_label = f"{away} @ {home}"
            print(f"\n  Analyzing: {game_label}")

            # Get best odds and market consensus
            best_odds = get_best_odds(game_data)
            market_probs = get_consensus_no_vig_odds(game_data)

            # Find similar historical games
            similar = find_similar_games(
                home, away, standings, all_games, team_forms,
                n_similar=n_similar,
            )
            print(f"    Found {len(similar)} similar historical games")

            # Get total and spread lines from odds
            # Prioritize theScore Bet lines, fallback to best odds
            total_line = None
            spread_line = None
            
            # Try to get theScore lines first
            thescore_odds = best_odds.get("all_books", {}).get("thescore", {})
            if thescore_odds.get("total_over"):
                total_line = thescore_odds["total_over"]["point"]
            elif best_odds["total"]["over"]:
                total_line = best_odds["total"]["over"]["point"]
            
            if thescore_odds.get("spread_home"):
                spread_line = thescore_odds["spread_home"]["point"]
            elif best_odds["spread"]["home"]:
                spread_line = best_odds["spread"]["home"]["point"]

            # Estimate true probabilities from similar games
            model_probs = estimate_probabilities(
                similar, home, away,
                total_line=total_line,
                spread_line=spread_line,
            )
            
            # Get ML predictions and blend with similarity model
            # Fetch player data (rest days, back-to-back, etc.)
            game_date = game_data["commence_time"][:10]
            player_data = get_player_data_nhl_api_only(home, away, game_date)
            
            # Add goalie data to player_data
            home_goalie_info = goalie_starters.get(home, {}).get('starter')
            away_goalie_info = goalie_starters.get(away, {}).get('starter')
            
            if home_goalie_info:
                player_data['home_goalie_stats'] = {
                    'save_pct': home_goalie_info['stats'].get('save_pct', 0.910),
                    'gaa': home_goalie_info['stats'].get('gaa', 2.80),
                    'quality_score': home_goalie_info.get('quality_score', 50),
                    # Recent form (last 10 starts)
                    'recent_save_pct': home_goalie_info['stats'].get('recent_save_pct', 0.910),
                    'recent_gaa': home_goalie_info['stats'].get('recent_gaa', 2.80),
                    'recent_quality_starts': home_goalie_info['stats'].get('recent_quality_starts', 5),
                }
            
            if away_goalie_info:
                player_data['away_goalie_stats'] = {
                    'save_pct': away_goalie_info['stats'].get('save_pct', 0.910),
                    'gaa': away_goalie_info['stats'].get('gaa', 2.80),
                    'quality_score': away_goalie_info.get('quality_score', 50),
                    # Recent form (last 10 starts)
                    'recent_save_pct': away_goalie_info['stats'].get('recent_save_pct', 0.910),
                    'recent_gaa': away_goalie_info['stats'].get('recent_gaa', 2.80),
                    'recent_quality_starts': away_goalie_info['stats'].get('recent_quality_starts', 5),
                }
            
            # Add injury data to player_data (for display, not for manual adjustment)
            from src.analysis.injury_tracker import calculate_injury_impact
            home_injuries = all_injuries.get(home, [])
            away_injuries = all_injuries.get(away, [])

            home_injury_impact = calculate_injury_impact(home_injuries, home)
            away_injury_impact = calculate_injury_impact(away_injuries, away)

            player_data['home_injury_impact'] = home_injury_impact['impact_score']
            player_data['away_injury_impact'] = away_injury_impact['impact_score']

            # Use pre-computed data instead of per-game fetches
            player_data['home_advanced_stats'] = team_advanced_cache.get(home, {})
            player_data['away_advanced_stats'] = team_advanced_cache.get(away, {})

            # Add streak momentum
            player_data['home_streak'] = team_current_streak.get(home, 0)
            player_data['away_streak'] = team_current_streak.get(away, 0)

            # Add special teams stats
            player_data['home_special_teams'] = team_special_teams_cache.get(home, {})
            player_data['away_special_teams'] = team_special_teams_cache.get(away, {})

            # Add H2H and form trends
            player_data['h2h_home_win_rate'] = h2h_records.get((home, away), 0.5)
            player_data['home_form_trend'] = form_trends.get(home, 0.0)

            home_splits = team_splits_cache.get(home, {'home_recent': {}, 'road_recent': {}})
            away_splits = team_splits_cache.get(away, {'home_recent': {}, 'road_recent': {}})
            
            player_data['home_team_splits'] = home_splits['home_recent']  # Home team at home
            player_data['away_team_splits'] = away_splits['road_recent']  # Away team on road
            
            home_stats_blend = {**standings[home], **{"win_pct": standings[home].get("win_pct", 0.5)}}
            away_stats_blend = {**standings[away], **{"win_pct": standings[away].get("win_pct", 0.5)}}
            
            # Try enhanced prediction with player data first
            ml_pred = ml_model.predict_with_context(
                home_stats_blend, away_stats_blend, 
                team_forms[home], team_forms[away],
                player_data
            )
            
            if ml_pred:
                # Blend ML with similarity model (52% similarity, 48% ML)
                # OPTIMIZED: Increased ML weight from 45% to 48% based on calibration analysis
                # Analysis showed model was underconfident - actual win rate 60% vs predicted 52.9%
                # 48% weight should find 10-25% more +EV bets and improve calibration
                model_probs_enhanced = blend_ml_and_similarity(ml_pred, model_probs, ml_weight=0.48)
                model_probs["home_win_prob"] = model_probs_enhanced["home_win_prob"]
                model_probs["away_win_prob"] = model_probs_enhanced["away_win_prob"]
                model_probs["expected_total"] = model_probs_enhanced["expected_total"]
                
                # Show adjustments if any were applied
                adjustments = ml_pred.get('adjustments_applied', {})
                adjustment_text = ""
                if adjustments.get('factors'):
                    factors_str = ', '.join(adjustments['factors'])
                    win_adj = adjustments.get('win_prob_adjustment', 0)
                    total_adj = adjustments.get('total_adjustment', 0)
                    adjustment_text = f" [Adj: {win_adj:+.1%} win, {total_adj:+.1f} goals | {factors_str}]"
                
                # Add player context indicators
                player_indicators = []
                if player_data.get('home_back_to_back'):
                    player_indicators.append(f"{home} B2B")
                if player_data.get('away_back_to_back'):
                    player_indicators.append(f"{away} B2B")
                if player_data.get('home_rest_days', 1) >= 3:
                    player_indicators.append(f"{home} well-rested")
                if player_data.get('away_rest_days', 1) >= 3:
                    player_indicators.append(f"{away} well-rested")
                
                # Add home/road split indicators
                home_home_splits = player_data.get('home_team_splits', {})
                away_road_splits = player_data.get('away_team_splits', {})
                
                if home_home_splits.get('win_pct', 0.5) > 0.7:
                    player_indicators.append(f"{home} strong at home")
                elif home_home_splits.get('win_pct', 0.5) < 0.3:
                    player_indicators.append(f"{home} weak at home")
                
                if away_road_splits.get('win_pct', 0.5) > 0.7:
                    player_indicators.append(f"{away} strong on road")
                elif away_road_splits.get('win_pct', 0.5) < 0.3:
                    player_indicators.append(f"{away} weak on road")
                
                # Add goalie recent form indicators
                home_goalie_stats = player_data.get('home_goalie_stats', {})
                away_goalie_stats = player_data.get('away_goalie_stats', {})
                
                if home_goalie_stats.get('recent_save_pct', 0.910) > 0.930:
                    player_indicators.append(f"{home} G hot")
                elif home_goalie_stats.get('recent_save_pct', 0.910) < 0.890:
                    player_indicators.append(f"{home} G cold")
                
                if away_goalie_stats.get('recent_save_pct', 0.910) > 0.930:
                    player_indicators.append(f"{away} G hot")
                elif away_goalie_stats.get('recent_save_pct', 0.910) < 0.890:
                    player_indicators.append(f"{away} G cold")
                
                player_context = f" [{', '.join(player_indicators)}]" if player_indicators else ""
            else:
                player_context = ""

            # Blend model with market
            # No post-blend manual adjustments — all contextual factors (B2B, goalie,
            # splits, rest) are incorporated as ML features so XGBoost learns optimal
            # weights. Analysis of 575 games showed manual adjustments hurt performance.
            blended = blend_model_and_market(model_probs, market_probs)

            # Print analysis
            line_source = "theScore" if thescore_odds.get("total_over") else "best available"
            ml_indicator = " (ML+Context)" if ml_pred else ""
            
            # Add goalie context with confirmation status
            goalie_context = ""
            goalie_status_text = ""
            if home_goalie_info and away_goalie_info:
                home_q = home_goalie_info.get('quality_score', 50)
                away_q = away_goalie_info.get('quality_score', 50)
                goalie_diff = home_q - away_q
                
                # Add confirmation status
                home_status = home_goalie_info.get('status', 'projected')
                away_status = away_goalie_info.get('status', 'projected')
                
                if home_status == 'confirmed' and away_status == 'confirmed':
                    goalie_status_text = " ✓"
                elif home_status == 'confirmed' or away_status == 'confirmed':
                    goalie_status_text = " ✓?"
                else:
                    goalie_status_text = " ?"
                
                if abs(goalie_diff) > 10:
                    advantage_team = home if goalie_diff > 0 else away
                    goalie_context = f" [Goalie{goalie_status_text}: {advantage_team} +{abs(goalie_diff):.0f}]"
                elif goalie_status_text:
                    goalie_context = f" [Goalies{goalie_status_text}]"
            
            # Add injury context (threshold raised: new scale is 0-30+, not 0-10)
            injury_context = ""
            if home_injury_impact['impact_score'] > 5 or away_injury_impact['impact_score'] > 5:
                injury_parts = []
                if home_injury_impact['impact_score'] > 5:
                    injury_parts.append(f"{home} -{home_injury_impact['impact_score']:.1f}")
                if away_injury_impact['impact_score'] > 5:
                    injury_parts.append(f"{away} -{away_injury_impact['impact_score']:.1f}")
                if injury_parts:
                    injury_context = f" [Injuries: {', '.join(injury_parts)}]"
            
            # Build context factors text from ML model
            context_factors_text = ""
            if ml_pred:
                factors = ml_pred.get('adjustments_applied', {}).get('factors', [])
                if factors:
                    context_factors_text = f" [Context: {', '.join(factors)}]"

            print(f"    Model{ml_indicator}: {home} {model_probs['home_win_prob']:.1%} / "
                  f"{away} {model_probs['away_win_prob']:.1%} "
                  f"(confidence: {model_probs['confidence']:.0%}){player_context}{goalie_context}{injury_context}{context_factors_text}")
            print(f"    Market: {home} {market_probs['home_win_prob']:.1%} / "
                  f"{away} {market_probs['away_win_prob']:.1%}")
            print(f"    Blended: {home} {blended['home_win_prob']:.1%} / "
                  f"{away} {blended['away_win_prob']:.1%}")
            if total_line:
                print(f"    Total: line {total_line} ({line_source}), model expects "
                      f"{model_probs['expected_total']:.1f} goals "
                      f"(O {blended['over_prob']:.1%} / U {blended['under_prob']:.1%})")

            # Find +EV bets
            game_bets = evaluate_all_bets(
                game_label, home, away,
                blended, best_odds,
                stake=stake, min_edge=min_edge,
                conservative=conservative,
                book_filter=book_filter,
            )
            # Attach all_book_odds to each bet for line shopping UI
            all_books = best_odds.get("all_books", {})
            for bet in game_bets:
                bet_type = bet.get("bet_type", "")
                pick = bet.get("pick", "")
                book_odds_list = []
                for bk, bk_odds in all_books.items():
                    if bet_type == "Moneyline":
                        # Determine which side this bet is on
                        side = "home" if home in pick else "away"
                        key = f"ml_{side}"
                        if key in bk_odds:
                            book_odds_list.append({
                                "book": bk,
                                "odds": bk_odds[key],
                            })
                    elif bet_type == "Total":
                        side = "over" if "Over" in pick else "under"
                        key = f"total_{side}"
                        if key in bk_odds:
                            book_odds_list.append({
                                "book": bk,
                                "odds": bk_odds[key]["price"],
                                "point": bk_odds[key]["point"],
                            })
                    elif bet_type == "Spread":
                        side = "home" if home in pick else "away"
                        key = f"spread_{side}"
                        if key in bk_odds:
                            book_odds_list.append({
                                "book": bk,
                                "odds": bk_odds[key]["price"],
                                "point": bk_odds[key]["point"],
                            })
                # Sort by best odds first
                book_odds_list.sort(key=lambda x: x["odds"], reverse=True)
                bet["all_book_odds"] = book_odds_list

            if game_bets:
                print(f"    >>> Found {len(game_bets)} +EV bets!")
            else:
                print(f"    No +EV bets at current lines")

            all_bets.extend(game_bets)
            # Collect context indicators for UI
            context_indicators = {
                "fatigue": [],
                "goalie": [],
                "injuries": [],
                "splits": [],
                "advanced": []
            }
            
            # Fatigue indicators
            if player_data.get('home_back_to_back'):
                context_indicators["fatigue"].append({"team": home, "type": "B2B", "severity": "medium"})
            if player_data.get('away_back_to_back'):
                context_indicators["fatigue"].append({"team": away, "type": "B2B", "severity": "medium"})
            if player_data.get('home_rest_days', 1) >= 3:
                context_indicators["fatigue"].append({"team": home, "type": "well-rested", "severity": "positive"})
            if player_data.get('away_rest_days', 1) >= 3:
                context_indicators["fatigue"].append({"team": away, "type": "well-rested", "severity": "positive"})
            
            # Goalie indicators
            home_goalie_stats = player_data.get('home_goalie_stats', {})
            away_goalie_stats = player_data.get('away_goalie_stats', {})
            
            if home_goalie_stats.get('recent_save_pct', 0.910) > 0.930:
                context_indicators["goalie"].append({"team": home, "type": "hot", "value": home_goalie_stats.get('recent_save_pct', 0), "severity": "positive"})
            elif home_goalie_stats.get('recent_save_pct', 0.910) < 0.890:
                context_indicators["goalie"].append({"team": home, "type": "cold", "value": home_goalie_stats.get('recent_save_pct', 0), "severity": "negative"})
            
            if away_goalie_stats.get('recent_save_pct', 0.910) > 0.930:
                context_indicators["goalie"].append({"team": away, "type": "hot", "value": away_goalie_stats.get('recent_save_pct', 0), "severity": "positive"})
            elif away_goalie_stats.get('recent_save_pct', 0.910) < 0.890:
                context_indicators["goalie"].append({"team": away, "type": "cold", "value": away_goalie_stats.get('recent_save_pct', 0), "severity": "negative"})
            
            # Goalie advantage
            if home_goalie_info and away_goalie_info:
                home_q = home_goalie_info.get('quality_score', 50)
                away_q = away_goalie_info.get('quality_score', 50)
                goalie_diff = home_q - away_q
                
                if abs(goalie_diff) > 10:
                    advantage_team = home if goalie_diff > 0 else away
                    context_indicators["goalie"].append({
                        "team": advantage_team,
                        "type": "advantage",
                        "value": abs(goalie_diff),
                        "severity": "positive"
                    })
            
            # Injury indicators (new scale: 0-30+, meaningful threshold ~5)
            if home_injury_impact['impact_score'] > 5:
                context_indicators["injuries"].append({
                    "team": home,
                    "impact": home_injury_impact['impact_score'],
                    "severity": "high" if home_injury_impact['impact_score'] > 12 else "negative"
                })
            if away_injury_impact['impact_score'] > 5:
                context_indicators["injuries"].append({
                    "team": away,
                    "impact": away_injury_impact['impact_score'],
                    "severity": "high" if away_injury_impact['impact_score'] > 12 else "negative"
                })
            
            # Home/road split indicators
            home_home_splits = player_data.get('home_team_splits', {})
            away_road_splits = player_data.get('away_team_splits', {})
            
            if home_home_splits.get('win_pct', 0.5) > 0.7:
                context_indicators["splits"].append({
                    "team": home,
                    "type": "strong_home",
                    "value": home_home_splits.get('win_pct', 0),
                    "severity": "positive"
                })
            elif home_home_splits.get('win_pct', 0.5) < 0.3:
                context_indicators["splits"].append({
                    "team": home,
                    "type": "weak_home",
                    "value": home_home_splits.get('win_pct', 0),
                    "severity": "negative"
                })
            
            if away_road_splits.get('win_pct', 0.5) > 0.7:
                context_indicators["splits"].append({
                    "team": away,
                    "type": "strong_road",
                    "value": away_road_splits.get('win_pct', 0),
                    "severity": "positive"
                })
            elif away_road_splits.get('win_pct', 0.5) < 0.3:
                context_indicators["splits"].append({
                    "team": away,
                    "type": "weak_road",
                    "value": away_road_splits.get('win_pct', 0),
                    "severity": "negative"
                })
            
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
                "goalie_matchup": {
                    "home": {
                        "name": home_goalie_info['name'] if home_goalie_info else "Unknown",
                        "quality_score": home_goalie_info.get('quality_score', 50) if home_goalie_info else 50,
                        "recent_save_pct": home_goalie_stats.get('recent_save_pct', 0.910),
                        "recent_gaa": home_goalie_stats.get('recent_gaa', 2.80),
                        "recent_quality_starts": home_goalie_stats.get('recent_quality_starts', 5),
                    } if home_goalie_info else None,
                    "away": {
                        "name": away_goalie_info['name'] if away_goalie_info else "Unknown",
                        "quality_score": away_goalie_info.get('quality_score', 50) if away_goalie_info else 50,
                        "recent_save_pct": away_goalie_stats.get('recent_save_pct', 0.910),
                        "recent_gaa": away_goalie_stats.get('recent_gaa', 2.80),
                        "recent_quality_starts": away_goalie_stats.get('recent_quality_starts', 5),
                    } if away_goalie_info else None,
                },
                "team_splits": {
                    "home": home_home_splits,
                    "away": away_road_splits,
                },
                "injuries": {
                    "home": home_injury_impact,
                    "away": away_injury_impact,
                },
                "advanced_stats": {
                    "home": player_data.get('home_advanced_stats', {}),
                    "away": player_data.get('away_advanced_stats', {}),
                }
            })

    else:
        # No odds - just show model analysis for today's games
        print("  Running in historical-only mode (no live odds)")
        todays_games = fetch_todays_games()
        if not todays_games:
            print("  No games scheduled today.")

        for game in todays_games:
            home = game["home_team"]
            away = game["away_team"]
            game_label = f"{away} @ {home}"

            if home not in standings or away not in standings:
                continue

            print(f"\n  Analyzing: {game_label}")

            similar = find_similar_games(
                home, away, standings, all_games, team_forms,
                n_similar=n_similar,
            )

            model_probs = estimate_probabilities(similar, home, away)

            print(f"    Model: {home} {model_probs['home_win_prob']:.1%} / "
                  f"{away} {model_probs['away_win_prob']:.1%}")
            print(f"    Expected total: {model_probs['expected_total']:.1f} goals")
            print(f"    Confidence: {model_probs['confidence']:.0%}")
            print(f"    Based on {len(similar)} similar games")

            game_analyses.append({
                "game": game_label,
                "home": home,
                "away": away,
                "model_probs": model_probs,
            })

    # Print recommendations
    print("\n")
    report = format_recommendations(all_bets, top_n=15, quota_info=quota_info)
    print(report)
    
    # Show past performance if available
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
        
        # Show by grade
        if stats.get('by_grade'):
            print("\n  By Grade:")
            for grade in ["A", "B+", "B", "C+"]:
                if grade in stats['by_grade']:
                    g = stats['by_grade'][grade]
                    win_rate = g['won'] / len(g['bets']) if g['bets'] else 0
                    roi = g['profit'] / g['staked'] if g['staked'] > 0 else 0
                    print(f"    [{grade:3s}] {len(g['bets']):2d} bets | "
                          f"Win: {win_rate:.1%} | "
                          f"ROI: {roi:+.1%}")
        
        print("=" * 75)
        print("  Run 'python bet_tracker.py --check' to update results")
        print()

    # Save results
    output = {
        "timestamp": datetime.now(EST).isoformat(),
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

    output_path = Path(__file__).parent / "data" / "latest_analysis.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"Full analysis saved to: {output_path}")
    
    # Save to history (with deduplication and 30-day rolling window)
    save_analysis(output)
    
    # Show history stats
    hist_stats = get_history_stats(days_back=7)
    if hist_stats:
        print(f"  📊 History: {hist_stats['total_analyses']} analyses, "
              f"{hist_stats['total_bets_recommended']} bets in last 7 days")

    return all_bets, game_analyses


def main():
    parser = argparse.ArgumentParser(description="NHL +EV Betting Finder")
    parser.add_argument("--stake", type=float, default=1.00,
                        help="Stake per bet in CAD (default: 1.00)")
    parser.add_argument("--days", type=int, default=90,
                        help="Historical lookback in days (default: 90)")
    parser.add_argument("--min-edge", type=float, default=0.02,
                        help="Minimum edge to recommend (default: 0.02 = 2%%)")
    parser.add_argument("--no-odds", action="store_true",
                        help="Run without live odds (no API key needed)")
    parser.add_argument("--similar", type=int, default=50,
                        help="Number of similar games to use (default: 50)")
    parser.add_argument("--conservative", action="store_true", default=True,
                        help="Conservative mode: totals + ML only, higher min edge, cap unrealistic edges")
    parser.add_argument("--with-spreads", action="store_true",
                        help="Include spread bets (disabled by default, spread model unreliable)")
    parser.add_argument("--all-books", action="store_true",
                        help="Include all books (default: filter out sharp books where model has no edge)")
    args = parser.parse_args()

    run_analysis(
        stake=args.stake,
        days_back=args.days,
        min_edge=args.min_edge,
        use_odds=not args.no_odds,
        n_similar=args.similar,
        conservative=not args.with_spreads,
        book_filter="all" if args.all_books else "soft",
    )


if __name__ == "__main__":
    main()
