"""
Backtest Model Performance
Analyze what the model would have predicted vs actual results for past games.
"""

import json
from datetime import datetime, timedelta
from src.data.nhl_data import fetch_season_games, fetch_standings, get_team_recent_form
from src.models.model import estimate_probabilities, find_similar_games
from src.models.ml_model_streamlined import StreamlinedNHLMLModel
from src.models.ml_model import blend_ml_and_similarity
import numpy as np


def backtest_last_n_games(n_games=50):
    """
    Backtest the model on the last n completed games.
    Compare model predictions to actual outcomes.
    """
    print("=" * 80)
    print(f"BACKTESTING MODEL ON LAST {n_games} GAMES")
    print("=" * 80)
    print()
    
    # Get historical data
    print("Fetching historical games...")
    all_games = fetch_season_games(days_back=90)
    standings = fetch_standings()
    
    # Calculate team forms
    print("Calculating team forms...")
    team_forms = {}
    for team in standings.keys():
        team_forms[team] = get_team_recent_form(team, all_games, n=10)
    
    # Load ML model
    print("Loading ML model...")
    ml_model = StreamlinedNHLMLModel()
    if not ml_model.load_models():
        print("Training model...")
        ml_model.train(all_games, standings, team_forms)
    
    # Get last n games
    recent_games = sorted(all_games, key=lambda x: x['date'], reverse=True)[:n_games]
    
    print(f"Analyzing {len(recent_games)} games...")
    print()
    
    results = {
        'total_games': 0,
        'correct_winner': 0,
        'correct_total_direction': 0,
        'avg_win_prob_error': [],
        'avg_total_error': [],
        'calibration_buckets': {
            '50-60%': {'predicted': 0, 'actual': 0},
            '60-70%': {'predicted': 0, 'actual': 0},
            '70-80%': {'predicted': 0, 'actual': 0},
            '80-90%': {'predicted': 0, 'actual': 0},
            '90-100%': {'predicted': 0, 'actual': 0},
        },
        'games': []
    }
    
    for game in recent_games:
        home = game['home_team']
        away = game['away_team']
        home_score = game['home_score']
        away_score = game['away_score']
        total = home_score + away_score
        home_won = home_score > away_score
        
        # Find similar games (excluding this game)
        other_games = [g for g in all_games if g['date'] != game['date'] or 
                       g['home_team'] != home or g['away_team'] != away]
        
        # Get model prediction
        try:
            # Find similar games
            similar_games = find_similar_games(
                home, away,
                standings, other_games, team_forms,
                n_similar=50
            )
            
            # Similarity model
            similar_list = [g[0] for g in similar_games]  # Extract games from tuples
            similar = estimate_probabilities(
                similar_list, home, away,
                total_line=6.5,
                spread_line=-1.5
            )
            
            # ML model
            home_stats = {**standings[home], **{"win_pct": standings[home].get("win_pct", 0.5)}}
            away_stats = {**standings[away], **{"win_pct": standings[away].get("win_pct", 0.5)}}
            
            ml_pred = ml_model.predict_with_context(
                home_stats, away_stats,
                team_forms[home], team_forms[away],
                {}  # No player data for backtest
            )
            
            if ml_pred:
                # Blend predictions
                blended = blend_ml_and_similarity(ml_pred, similar, ml_weight=0.45)
                home_win_prob = blended['home_win_prob']
                expected_total = blended['expected_total']
            else:
                home_win_prob = similar['home_win_prob']
                expected_total = similar['expected_total']
            
            # Record results
            results['total_games'] += 1
            
            # Winner prediction
            predicted_home_win = home_win_prob > 0.5
            if predicted_home_win == home_won:
                results['correct_winner'] += 1
            
            # Total prediction
            predicted_over = expected_total > 6.5
            actual_over = total > 6.5
            if predicted_over == actual_over:
                results['correct_total_direction'] += 1
            
            # Probability calibration
            if home_win_prob >= 0.5:
                bucket = None
                if 0.5 <= home_win_prob < 0.6:
                    bucket = '50-60%'
                elif 0.6 <= home_win_prob < 0.7:
                    bucket = '60-70%'
                elif 0.7 <= home_win_prob < 0.8:
                    bucket = '70-80%'
                elif 0.8 <= home_win_prob < 0.9:
                    bucket = '80-90%'
                elif home_win_prob >= 0.9:
                    bucket = '90-100%'
                
                if bucket:
                    results['calibration_buckets'][bucket]['predicted'] += 1
                    if home_won:
                        results['calibration_buckets'][bucket]['actual'] += 1
            
            # Errors
            results['avg_win_prob_error'].append(abs(home_win_prob - (1 if home_won else 0)))
            results['avg_total_error'].append(abs(expected_total - total))
            
            # Store game details
            results['games'].append({
                'date': game['date'],
                'matchup': f"{away} @ {home}",
                'score': f"{away_score}-{home_score}",
                'predicted_home_win_prob': home_win_prob,
                'predicted_total': expected_total,
                'actual_home_won': home_won,
                'actual_total': total,
                'winner_correct': predicted_home_win == home_won,
                'total_correct': predicted_over == actual_over
            })
            
        except Exception as e:
            print(f"  Error analyzing {away} @ {home}: {e}")
            continue
    
    # Print results
    print("=" * 80)
    print("BACKTEST RESULTS")
    print("=" * 80)
    print()
    
    print(f"Games Analyzed: {results['total_games']}")
    print()
    
    print("WINNER PREDICTION:")
    win_acc = results['correct_winner'] / results['total_games'] * 100
    print(f"  Correct: {results['correct_winner']}/{results['total_games']} ({win_acc:.1f}%)")
    print()
    
    print("TOTAL PREDICTION (Over/Under 6.5):")
    total_acc = results['correct_total_direction'] / results['total_games'] * 100
    print(f"  Correct: {results['correct_total_direction']}/{results['total_games']} ({total_acc:.1f}%)")
    print()
    
    print("AVERAGE ERRORS:")
    avg_prob_error = np.mean(results['avg_win_prob_error'])
    avg_total_error = np.mean(results['avg_total_error'])
    print(f"  Win Probability Error: {avg_prob_error:.3f}")
    print(f"  Total Goals Error: {avg_total_error:.2f} goals")
    print()
    
    print("PROBABILITY CALIBRATION:")
    print("  (How often does a 60% prediction actually win 60% of the time?)")
    print()
    for bucket, data in results['calibration_buckets'].items():
        if data['predicted'] > 0:
            actual_rate = data['actual'] / data['predicted'] * 100
            print(f"  {bucket}: {data['actual']}/{data['predicted']} = {actual_rate:.1f}% actual win rate")
    print()
    
    print("=" * 80)
    print("RECENT GAMES BREAKDOWN")
    print("=" * 80)
    print()
    
    # Show last 20 games
    for game in results['games'][:20]:
        status = "✅" if game['winner_correct'] else "❌"
        print(f"{status} {game['date']} | {game['matchup']}")
        print(f"   Predicted: Home {game['predicted_home_win_prob']:.1%} | Total {game['predicted_total']:.1f}")
        print(f"   Actual: {game['score']} | Total {game['actual_total']}")
        print()
    
    # Save full results
    with open('backtest_results.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print("Full results saved to backtest_results.json")
    print()
    
    return results


if __name__ == '__main__':
    backtest_last_n_games(50)
