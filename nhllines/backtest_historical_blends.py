#!/usr/bin/env python3
"""
Backtest Different ML Blend Ratios on Historical Games

Uses the 575 historical games to simulate how different blend ratios
would have performed. This gives us much more data than waiting for
real-time bet results.
"""

import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import statistics

# Import the necessary modules
import sys
sys.path.insert(0, str(Path(__file__).parent))

from src.data import fetch_standings, fetch_season_games, get_team_recent_form
from src.models.ml_model import NHLMLModel, blend_ml_and_similarity
from src.analysis import calculate_ev
import math

def load_historical_games():
    """Load historical games from cache"""
    cache_path = Path("cache/season_games_20252026_90.json")
    if not cache_path.exists():
        print("❌ No cached games found. Run main.py first.")
        return []
    
    with open(cache_path) as f:
        return json.load(f)

def simulate_game_prediction(game, ml_model, standings, team_forms, ml_weight):
    """
    Simulate what the model would have predicted for a game
    at a given ML weight
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
        return None
    
    # Get actual outcome
    home_score = game.get('home_score', 0)
    away_score = game.get('away_score', 0)
    total_goals = home_score + away_score
    
    actual_home_win = home_score > away_score
    actual_away_win = away_score > home_score
    
    # Get ML prediction (simplified - no player data for historical games)
    try:
        ml_pred = ml_model.predict_with_context(
            home_stats, away_stats,
            home_form, away_form,
            {}  # No player data for historical
        )
    except:
        return None
    
    if not ml_pred:
        return None
    
    # Create similarity-based prediction (simplified)
    # In reality, this would use the full similarity model
    # For backtest, we'll use a baseline based on standings
    home_win_pct = home_stats.get('win_pct', 0.5)
    away_win_pct = away_stats.get('win_pct', 0.5)
    
    # Normalize to probabilities
    total_pct = home_win_pct + away_win_pct
    if total_pct > 0:
        similarity_home_prob = home_win_pct / total_pct
    else:
        similarity_home_prob = 0.5
    
    similarity_probs = {
        'home_win_prob': similarity_home_prob,
        'away_win_prob': 1 - similarity_home_prob,
        'expected_total': 6.0,  # League average
    }
    
    # Blend predictions at specified weight
    blended = blend_ml_and_similarity(ml_pred, similarity_probs, ml_weight=ml_weight)
    
    return {
        'game': f"{away} @ {home}",
        'home': home,
        'away': away,
        'actual_home_win': actual_home_win,
        'actual_away_win': actual_away_win,
        'actual_total': total_goals,
        'predicted_home_prob': blended['home_win_prob'],
        'predicted_away_prob': blended['away_win_prob'],
        'predicted_total': blended['expected_total'],
        'ml_home_prob': ml_pred['home_win_prob'],
        'ml_away_prob': ml_pred['away_win_prob'],
        'similarity_home_prob': similarity_home_prob,
        'similarity_away_prob': 1 - similarity_home_prob,
    }

def calculate_brier_score(predictions):
    """Calculate Brier score (lower is better)"""
    scores = []
    for pred in predictions:
        # Home win prediction
        home_outcome = 1 if pred['actual_home_win'] else 0
        home_pred = pred['predicted_home_prob']
        scores.append((home_pred - home_outcome) ** 2)
        
        # Away win prediction
        away_outcome = 1 if pred['actual_away_win'] else 0
        away_pred = pred['predicted_away_prob']
        scores.append((away_pred - away_outcome) ** 2)
    
    return statistics.mean(scores) if scores else None

def calculate_log_loss(predictions):
    """Calculate log loss (lower is better)"""
    scores = []
    for pred in predictions:
        # Clip predictions to avoid log(0)
        home_pred = max(0.001, min(0.999, pred['predicted_home_prob']))
        away_pred = max(0.001, min(0.999, pred['predicted_away_prob']))
        
        if pred['actual_home_win']:
            scores.append(-1 * math.log(home_pred))
        elif pred['actual_away_win']:
            scores.append(-1 * math.log(away_pred))
    
    return statistics.mean(scores) if scores else None

def evaluate_calibration(predictions, num_buckets=10):
    """Evaluate how well predicted probabilities match actual outcomes"""
    buckets = defaultdict(lambda: {'predicted': [], 'actual': []})
    
    for pred in predictions:
        # Round to nearest bucket
        bucket = round(pred['predicted_home_prob'] * num_buckets) / num_buckets
        buckets[bucket]['predicted'].append(pred['predicted_home_prob'])
        buckets[bucket]['actual'].append(1 if pred['actual_home_win'] else 0)
    
    calibration_data = []
    for bucket in sorted(buckets.keys()):
        data = buckets[bucket]
        avg_predicted = statistics.mean(data['predicted'])
        avg_actual = statistics.mean(data['actual'])
        count = len(data['actual'])
        error = abs(avg_predicted - avg_actual)
        
        calibration_data.append({
            'bucket': bucket,
            'predicted': avg_predicted,
            'actual': avg_actual,
            'count': count,
            'error': error
        })
    
    return calibration_data

def main():
    print("=" * 80)
    print("  HISTORICAL BACKTEST: ML BLEND RATIO OPTIMIZATION")
    print("=" * 80)
    print()
    
    # Load historical games
    print("Loading historical games...")
    games = load_historical_games()
    print(f"✓ Loaded {len(games)} historical games")
    print()
    
    # Filter to completed games with scores
    completed_games = [g for g in games if g.get('home_score') is not None and g.get('away_score') is not None]
    print(f"✓ Found {len(completed_games)} completed games with scores")
    print()
    
    # Load standings and team forms
    print("Loading team data...")
    standings_dict = fetch_standings()
    
    # Get team forms
    team_forms = {}
    for team in standings_dict.keys():
        team_forms[team] = get_team_recent_form(team, games, n=10)
    
    print(f"✓ Loaded data for {len(standings_dict)} teams")
    print()
    
    # Initialize ML model
    print("Initializing ML model...")
    ml_model = NHLMLModel()
    ml_model.load_models()
    print("✓ ML model loaded")
    print()
    
    # Test different blend ratios
    blend_ratios = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]
    
    print("=" * 80)
    print("TESTING BLEND RATIOS")
    print("=" * 80)
    print()
    
    results = {}
    
    for ml_weight in blend_ratios:
        print(f"Testing ML weight: {ml_weight:.0%}...")
        
        predictions = []
        for game in completed_games[:200]:  # Test on first 200 games for speed
            pred = simulate_game_prediction(game, ml_model, standings_dict, team_forms, ml_weight)
            if pred:
                predictions.append(pred)
        
        if not predictions:
            print(f"  ⚠ No predictions generated")
            continue
        
        # Calculate metrics
        brier = calculate_brier_score(predictions)
        calibration = evaluate_calibration(predictions)
        
        # Calculate accuracy
        correct_home = sum(1 for p in predictions if p['actual_home_win'] and p['predicted_home_prob'] > 0.5)
        correct_away = sum(1 for p in predictions if p['actual_away_win'] and p['predicted_away_prob'] > 0.5)
        total_predictions = len(predictions)
        accuracy = (correct_home + correct_away) / total_predictions
        
        # Calculate mean calibration error
        mean_cal_error = statistics.mean([c['error'] for c in calibration])
        
        results[ml_weight] = {
            'predictions': len(predictions),
            'brier_score': brier,
            'accuracy': accuracy,
            'calibration': calibration,
            'mean_calibration_error': mean_cal_error,
        }
        
        print(f"  Predictions: {len(predictions)}")
        print(f"  Brier Score: {brier:.4f} (lower is better)")
        print(f"  Accuracy: {accuracy:.1%}")
        print(f"  Mean Calibration Error: {mean_cal_error:.1%}")
        print()
    
    # Summary
    print("=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)
    print()
    
    print("ML Weight | Brier Score | Accuracy | Calibration Error | Rank")
    print("-" * 80)
    
    # Sort by Brier score (lower is better)
    sorted_results = sorted(results.items(), key=lambda x: x[1]['brier_score'])
    
    for rank, (ml_weight, data) in enumerate(sorted_results, 1):
        print(f"{ml_weight:6.0%}    | {data['brier_score']:11.4f} | {data['accuracy']:8.1%} | "
              f"{data['mean_calibration_error']:17.1%} | #{rank}")
    
    print()
    
    # Best performer
    best_weight, best_data = sorted_results[0]
    print(f"BEST PERFORMER: {best_weight:.0%} ML weight")
    print(f"  Brier Score: {best_data['brier_score']:.4f}")
    print(f"  Accuracy: {best_data['accuracy']:.1%}")
    print(f"  Calibration Error: {best_data['mean_calibration_error']:.1%}")
    print()
    
    # Compare to current
    current_weight = 0.45
    if current_weight in results:
        current_data = results[current_weight]
        print(f"CURRENT SETTING: {current_weight:.0%} ML weight")
        print(f"  Brier Score: {current_data['brier_score']:.4f}")
        print(f"  Accuracy: {current_data['accuracy']:.1%}")
        print(f"  Calibration Error: {current_data['mean_calibration_error']:.1%}")
        print()
        
        if best_weight != current_weight:
            improvement = (current_data['brier_score'] - best_data['brier_score']) / current_data['brier_score'] * 100
            print(f"POTENTIAL IMPROVEMENT: {improvement:.1f}% better Brier score with {best_weight:.0%} weight")
        else:
            print("✓ Current setting is optimal!")
    
    print()
    print("=" * 80)
    print("RECOMMENDATION")
    print("=" * 80)
    print()
    
    # Check if difference is significant
    if best_weight == current_weight:
        print("✓ Current 45% ML weight is optimal based on historical data")
        print("  → No changes recommended")
    else:
        diff = abs(best_data['brier_score'] - results.get(current_weight, {}).get('brier_score', 0))
        if diff < 0.01:
            print("⚠ Difference between best and current is minimal (<0.01)")
            print(f"  → Current 45% weight performs nearly as well as {best_weight:.0%}")
            print("  → No urgent need to change")
        else:
            print(f"✓ Consider testing {best_weight:.0%} ML weight")
            print(f"  → Shows {improvement:.1f}% improvement in Brier score")
            print(f"  → Test with real bets to confirm")
    
    print()
    print("=" * 80)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        print()
        print("Note: This script requires the full model to be loaded.")
        print("Make sure you've run main.py at least once to train the models.")
