#!/usr/bin/env python3
"""
Full Season Backtest

Backtests different ML blend ratios on the entire 2025-26 NHL season
using historical game data and the actual model predictions.
"""

import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import statistics

# Import necessary modules
import sys
sys.path.insert(0, str(Path(__file__).parent))

from src.data import fetch_standings, fetch_season_games, get_team_recent_form
from src.models.ml_model import NHLMLModel, blend_ml_and_similarity
from src.analysis import calculate_ev

def load_historical_games():
    """Load all historical games from cache"""
    cache_path = Path("cache/season_games_20252026_90.json")
    if cache_path.exists():
        with open(cache_path) as f:
            return json.load(f)
    
    # If not cached, fetch
    print("Fetching season games...")
    games = fetch_season_games(days_back=90)
    return games

def simulate_bet_at_blend_ratio(game, ml_model, standings, team_forms, ml_weight, min_edge=0.02):
    """
    Simulate what bets would have been placed for a game at a given ML weight
    
    Returns list of bets that would have been placed
    """
    home = game['home_team']
    away = game['away_team']
    
    # Get team stats
    home_stats = standings.get(home, {})
    away_stats = standings.get(away, {})
    home_form = team_forms.get(home, {})
    away_form = team_forms.get(away, {})
    
    # Skip if missing data
    if not home_stats or not away_stats:
        return []
    
    # Get actual outcome
    home_score = game.get('home_score', 0)
    away_score = game.get('away_score', 0)
    total_goals = home_score + away_score
    
    actual_home_win = home_score > away_score
    actual_away_win = away_score > home_score
    
    # Get ML prediction
    try:
        ml_pred = ml_model.predict_with_context(
            home_stats, away_stats,
            home_form, away_form,
            {}  # No player data for historical
        )
    except:
        return []
    
    if not ml_pred:
        return []
    
    # Create similarity-based prediction (simplified)
    home_win_pct = home_stats.get('win_pct', 0.5)
    away_win_pct = away_stats.get('win_pct', 0.5)
    
    total_pct = home_win_pct + away_win_pct
    if total_pct > 0:
        similarity_home_prob = home_win_pct / total_pct
    else:
        similarity_home_prob = 0.5
    
    similarity_probs = {
        'home_win_prob': similarity_home_prob,
        'away_win_prob': 1 - similarity_home_prob,
        'expected_total': 6.0,
        'over_prob': 0.5,
        'under_prob': 0.5,
    }
    
    # Blend predictions at specified weight
    blended = blend_ml_and_similarity(ml_pred, similarity_probs, ml_weight=ml_weight)
    
    # Simulate market odds (simplified - use league average)
    # In reality, we'd need historical odds data
    # For backtest, assume market is reasonably efficient
    market_home_prob = 0.50  # Simplified
    market_away_prob = 0.50
    
    # Find bets with edge
    bets = []
    
    # Moneyline bets
    home_ml_edge = blended['home_win_prob'] - market_home_prob
    if home_ml_edge >= min_edge:
        # Calculate profit
        profit = 1.0 if actual_home_win else -0.5  # $0.50 stake
        bets.append({
            'type': 'Moneyline',
            'pick': f'{home} ML',
            'edge': home_ml_edge,
            'predicted_prob': blended['home_win_prob'],
            'actual_outcome': actual_home_win,
            'profit': profit,
            'stake': 0.5,
        })
    
    away_ml_edge = blended['away_win_prob'] - market_away_prob
    if away_ml_edge >= min_edge:
        profit = 1.0 if actual_away_win else -0.5
        bets.append({
            'type': 'Moneyline',
            'pick': f'{away} ML',
            'edge': away_ml_edge,
            'predicted_prob': blended['away_win_prob'],
            'actual_outcome': actual_away_win,
            'profit': profit,
            'stake': 0.5,
        })
    
    # Total bets (simplified)
    over_edge = blended.get('over_prob', 0.5) - 0.5
    if over_edge >= min_edge:
        actual_over = total_goals > 6.5
        profit = 1.0 if actual_over else -0.5
        bets.append({
            'type': 'Total',
            'pick': 'Over 6.5',
            'edge': over_edge,
            'predicted_prob': blended.get('over_prob', 0.5),
            'actual_outcome': actual_over,
            'profit': profit,
            'stake': 0.5,
        })
    
    under_edge = blended.get('under_prob', 0.5) - 0.5
    if under_edge >= min_edge:
        actual_under = total_goals < 6.5
        profit = 1.0 if actual_under else -0.5
        bets.append({
            'type': 'Total',
            'pick': 'Under 6.5',
            'edge': under_edge,
            'predicted_prob': blended.get('under_prob', 0.5),
            'actual_outcome': actual_under,
            'profit': profit,
            'stake': 0.5,
        })
    
    return bets

def backtest_season(ml_weights=[0.40, 0.45, 0.48, 0.50, 0.55]):
    """
    Backtest entire season at different ML weights
    """
    
    print("=" * 80)
    print("  FULL SEASON BACKTEST")
    print("=" * 80)
    print()
    
    # Load data
    print("Loading historical games...")
    games = load_historical_games()
    completed_games = [g for g in games if g.get('home_score') is not None]
    print(f"✓ Loaded {len(completed_games)} completed games")
    print()
    
    print("Loading team data...")
    standings = fetch_standings()
    
    team_forms = {}
    for team in standings.keys():
        team_forms[team] = get_team_recent_form(team, games, n=10)
    
    print(f"✓ Loaded data for {len(standings)} teams")
    print()
    
    print("Initializing ML model...")
    ml_model = NHLMLModel()
    ml_model.load_models()
    print("✓ ML model loaded")
    print()
    
    # Backtest each weight
    print("=" * 80)
    print("BACKTESTING DIFFERENT ML WEIGHTS")
    print("=" * 80)
    print()
    
    results = {}
    
    for ml_weight in ml_weights:
        print(f"Testing {ml_weight:.0%} ML weight...")
        
        all_bets = []
        games_processed = 0
        
        # Process games in batches for progress updates
        batch_size = 50
        for i in range(0, len(completed_games), batch_size):
            batch = completed_games[i:i+batch_size]
            
            for game in batch:
                bets = simulate_bet_at_blend_ratio(
                    game, ml_model, standings, team_forms, ml_weight
                )
                all_bets.extend(bets)
                games_processed += 1
            
            if games_processed % 100 == 0:
                print(f"  Processed {games_processed}/{len(completed_games)} games...")
        
        # Calculate metrics
        if not all_bets:
            print(f"  ⚠ No bets found")
            continue
        
        total_bets = len(all_bets)
        won_bets = sum(1 for b in all_bets if b['actual_outcome'])
        total_staked = sum(b['stake'] for b in all_bets)
        total_profit = sum(b['profit'] for b in all_bets)
        win_rate = won_bets / total_bets if total_bets > 0 else 0
        roi = (total_profit / total_staked * 100) if total_staked > 0 else 0
        avg_edge = statistics.mean([b['edge'] for b in all_bets]) * 100
        
        # Calculate by bet type
        by_type = defaultdict(lambda: {'bets': 0, 'won': 0, 'profit': 0, 'staked': 0})
        for bet in all_bets:
            bet_type = bet['type']
            by_type[bet_type]['bets'] += 1
            by_type[bet_type]['staked'] += bet['stake']
            by_type[bet_type]['profit'] += bet['profit']
            if bet['actual_outcome']:
                by_type[bet_type]['won'] += 1
        
        results[ml_weight] = {
            'total_bets': total_bets,
            'won_bets': won_bets,
            'win_rate': win_rate,
            'total_staked': total_staked,
            'total_profit': total_profit,
            'roi': roi,
            'avg_edge': avg_edge,
            'by_type': dict(by_type),
        }
        
        print(f"  ✓ Found {total_bets} bets")
        print(f"    Win Rate: {win_rate:.1%}")
        print(f"    ROI: {roi:+.1f}%")
        print(f"    Profit: ${total_profit:+.2f}")
        print()
    
    # Summary
    print("=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)
    print()
    
    print("ML Weight | Bets | Win Rate | ROI      | Profit   | Avg Edge | Rank")
    print("-" * 80)
    
    # Sort by ROI
    sorted_results = sorted(results.items(), key=lambda x: x[1]['roi'], reverse=True)
    
    for rank, (ml_weight, data) in enumerate(sorted_results, 1):
        print(f"{ml_weight:6.0%}    | {data['total_bets']:4d} | {data['win_rate']:8.1%} | "
              f"{data['roi']:+7.1f}% | ${data['total_profit']:+7.2f} | "
              f"{data['avg_edge']:8.1f}% | #{rank}")
    
    print()
    
    # Best performer
    best_weight, best_data = sorted_results[0]
    print(f"🏆 BEST PERFORMER: {best_weight:.0%} ML weight")
    print(f"   Bets: {best_data['total_bets']}")
    print(f"   Win Rate: {best_data['win_rate']:.1%}")
    print(f"   ROI: {best_data['roi']:+.1f}%")
    print(f"   Profit: ${best_data['total_profit']:+.2f}")
    print()
    
    # Compare to current
    current_weight = 0.48
    if current_weight in results:
        current_data = results[current_weight]
        current_rank = [i for i, (w, _) in enumerate(sorted_results, 1) if w == current_weight][0]
        
        print(f"📊 CURRENT SETTING: {current_weight:.0%} ML weight (Rank #{current_rank})")
        print(f"   Bets: {current_data['total_bets']}")
        print(f"   Win Rate: {current_data['win_rate']:.1%}")
        print(f"   ROI: {current_data['roi']:+.1f}%")
        print(f"   Profit: ${current_data['total_profit']:+.2f}")
        print()
        
        if best_weight != current_weight:
            profit_diff = best_data['total_profit'] - current_data['total_profit']
            roi_diff = best_data['roi'] - current_data['roi']
            print(f"   Difference from best:")
            print(f"   Profit: ${profit_diff:+.2f}")
            print(f"   ROI: {roi_diff:+.1f}%")
        else:
            print("   ✓ Current setting is optimal!")
    
    print()
    print("=" * 80)
    print("DETAILED BREAKDOWN BY BET TYPE")
    print("=" * 80)
    print()
    
    for ml_weight in sorted(results.keys()):
        data = results[ml_weight]
        print(f"{ml_weight:.0%} ML Weight:")
        
        for bet_type in sorted(data['by_type'].keys()):
            type_data = data['by_type'][bet_type]
            wr = type_data['won'] / type_data['bets'] if type_data['bets'] > 0 else 0
            roi = (type_data['profit'] / type_data['staked'] * 100) if type_data['staked'] > 0 else 0
            
            print(f"  {bet_type:12s}: {type_data['bets']:4d} bets | "
                  f"{wr:5.1%} WR | {roi:+7.1f}% ROI | ${type_data['profit']:+7.2f}")
        print()
    
    print("=" * 80)
    print("RECOMMENDATION")
    print("=" * 80)
    print()
    
    if best_weight == current_weight:
        print(f"✓ Current {current_weight:.0%} ML weight is optimal based on full season backtest")
        print("  → No changes recommended")
    else:
        profit_improvement = best_data['total_profit'] - results[current_weight]['total_profit']
        roi_improvement = best_data['roi'] - results[current_weight]['roi']
        
        print(f"⚠ Backtest suggests {best_weight:.0%} ML weight may be better")
        print(f"  → Potential improvement: ${profit_improvement:+.2f} profit ({roi_improvement:+.1f}% ROI)")
        print()
        print("  However, consider:")
        print("  • This is a simplified backtest (no real odds data)")
        print("  • Real-world performance may differ")
        print("  • Current 48% weight based on recent calibration analysis")
        print("  • Recommend monitoring 48% performance before changing")
    
    print()
    print("=" * 80)
    
    return results

if __name__ == "__main__":
    try:
        results = backtest_season()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        print()
        print("Note: This backtest uses simplified assumptions:")
        print("  • No historical odds data (assumes efficient market)")
        print("  • No player-level data for historical games")
        print("  • Simplified bet evaluation")
        print()
        print("Results should be used as directional guidance, not absolute truth.")
