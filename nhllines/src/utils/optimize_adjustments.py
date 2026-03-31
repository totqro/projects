"""
Optimize Adjustment Weights Based on Historical Performance
Analyzes bet results to find optimal adjustment weights.
"""

import json
import numpy as np
from scipy.optimize import minimize
from collections import defaultdict


def load_bet_results():
    """Load historical bet results."""
    with open('bet_results.json', 'r') as f:
        data = json.load(f)
    return data.get('results', {})


def load_analysis_history():
    """Load analysis history to get game context."""
    with open('analysis_history.json', 'r') as f:
        data = json.load(f)
    return data.get('analyses', [])


def extract_adjustment_factors(bet, game_analysis):
    """
    Extract which adjustment factors were present for a bet.
    Returns dict of factor presence (0 or 1).
    """
    factors = {
        'home_goalie_hot': 0,
        'home_goalie_cold': 0,
        'away_goalie_hot': 0,
        'away_goalie_cold': 0,
        'goalie_quality_advantage': 0,
        'home_injuries': 0,
        'away_injuries': 0,
        'home_back_to_back': 0,
        'away_back_to_back': 0,
        'strong_home': 0,
        'weak_home': 0,
        'strong_road': 0,
        'weak_road': 0,
    }
    
    if not game_analysis:
        return factors
    
    context = game_analysis.get('context_indicators', {})
    
    # Goalie factors
    for goalie in context.get('goalie', []):
        if goalie['type'] == 'hot':
            if goalie['team'] == game_analysis['home']:
                factors['home_goalie_hot'] = 1
            else:
                factors['away_goalie_hot'] = 1
        elif goalie['type'] == 'cold':
            if goalie['team'] == game_analysis['home']:
                factors['home_goalie_cold'] = 1
            else:
                factors['away_goalie_cold'] = 1
        elif goalie['type'] == 'advantage':
            factors['goalie_quality_advantage'] = goalie['value'] / 10  # Normalize
    
    # Injury factors
    for injury in context.get('injuries', []):
        if injury['team'] == game_analysis['home']:
            factors['home_injuries'] = injury['impact'] / 5  # Normalize
        else:
            factors['away_injuries'] = injury['impact'] / 5
    
    # Fatigue factors
    for fatigue in context.get('fatigue', []):
        if fatigue['type'] == 'B2B':
            if fatigue['team'] == game_analysis['home']:
                factors['home_back_to_back'] = 1
            else:
                factors['away_back_to_back'] = 1
    
    # Splits factors
    for split in context.get('splits', []):
        if split['type'] == 'strong_home' and split['team'] == game_analysis['home']:
            factors['strong_home'] = 1
        elif split['type'] == 'weak_home' and split['team'] == game_analysis['home']:
            factors['weak_home'] = 1
        elif split['type'] == 'strong_road' and split['team'] == game_analysis['away']:
            factors['strong_road'] = 1
        elif split['type'] == 'weak_road' and split['team'] == game_analysis['away']:
            factors['weak_road'] = 1
    
    return factors


def analyze_factor_impact():
    """
    Analyze the actual impact of each factor on bet outcomes.
    """
    results = load_bet_results()
    analyses = load_analysis_history()
    
    # Create lookup for game analyses
    game_lookup = {}
    for analysis in analyses:
        for game in analysis.get('games_analyzed', []):
            key = game['game']
            game_lookup[key] = game
    
    # Collect data for each factor
    factor_data = defaultdict(lambda: {'with': [], 'without': []})
    
    for bet_id, result in results.items():
        bet = result['bet']
        game_key = bet['game']
        
        # Find corresponding game analysis
        game_analysis = game_lookup.get(game_key)
        if not game_analysis:
            continue
        
        # Extract factors
        factors = extract_adjustment_factors(bet, game_analysis)
        
        # Record outcome (1 = won, 0 = lost)
        outcome = 1 if result['result'] == 'won' else 0
        
        # Track each factor
        for factor_name, factor_value in factors.items():
            if factor_value > 0:
                factor_data[factor_name]['with'].append(outcome)
            else:
                factor_data[factor_name]['without'].append(outcome)
    
    # Calculate impact for each factor
    print('=' * 80)
    print('FACTOR IMPACT ANALYSIS (Based on Historical Bets)')
    print('=' * 80)
    print()
    print(f'{"Factor":<30} | With Factor | Without Factor | Impact')
    print('-' * 80)
    
    impacts = {}
    for factor, data in sorted(factor_data.items()):
        with_factor = data['with']
        without_factor = data['without']
        
        if len(with_factor) >= 2 and len(without_factor) >= 2:
            win_rate_with = np.mean(with_factor)
            win_rate_without = np.mean(without_factor)
            impact = win_rate_with - win_rate_without
            
            impacts[factor] = {
                'win_rate_with': win_rate_with,
                'win_rate_without': win_rate_without,
                'impact': impact,
                'sample_with': len(with_factor),
                'sample_without': len(without_factor)
            }
            
            print(f'{factor:<30} | {win_rate_with:5.1%} ({len(with_factor):2d}) | '
                  f'{win_rate_without:5.1%} ({len(without_factor):2d}) | {impact:+6.1%}')
    
    print('=' * 80)
    print()
    
    return impacts


def calculate_optimal_weights(impacts):
    """
    Calculate optimal adjustment weights based on observed impacts.
    """
    print('=' * 80)
    print('RECOMMENDED ADJUSTMENT WEIGHTS')
    print('=' * 80)
    print()
    
    # Map factors to adjustment weights
    # Positive impact = increase win probability
    # Negative impact = decrease win probability
    
    recommendations = {}
    
    print('Based on historical data:')
    print()
    
    for factor, data in sorted(impacts.items(), key=lambda x: abs(x[1]['impact']), reverse=True):
        impact = data['impact']
        sample = data['sample_with']
        
        # Only recommend if we have enough data (5+ samples)
        if sample < 5:
            print(f'{factor:<30}: Insufficient data ({sample} samples)')
            continue
        
        # Calculate confidence based on sample size
        confidence = min(1.0, sample / 10)
        
        # Recommended weight = observed impact * confidence
        # Cap at reasonable values
        recommended_weight = impact * confidence
        recommended_weight = max(-0.05, min(0.05, recommended_weight))  # Cap at ±5%
        
        recommendations[factor] = recommended_weight
        
        print(f'{factor:<30}: {recommended_weight:+.1%} (impact: {impact:+.1%}, n={sample})')
    
    print()
    print('=' * 80)
    
    return recommendations


def compare_to_current_weights():
    """Compare recommended weights to current weights."""
    current_weights = {
        'home_goalie_hot': +0.03,
        'home_goalie_cold': -0.03,
        'away_goalie_hot': -0.03,
        'away_goalie_cold': +0.03,
        'goalie_quality_advantage': +0.02,  # per 10 points
        'home_injuries': -0.02,  # per 5 impact
        'away_injuries': +0.02,
        'home_back_to_back': -0.02,
        'away_back_to_back': +0.02,
        'strong_home': +0.02,
        'weak_home': -0.02,
        'strong_road': -0.02,
        'weak_road': +0.02,
    }
    
    print('=' * 80)
    print('CURRENT vs RECOMMENDED WEIGHTS')
    print('=' * 80)
    print()
    print(f'{"Factor":<30} | Current | Recommended | Change')
    print('-' * 80)
    
    impacts = analyze_factor_impact()
    recommendations = calculate_optimal_weights(impacts)
    
    for factor in sorted(current_weights.keys()):
        current = current_weights.get(factor, 0)
        recommended = recommendations.get(factor, 0)
        change = recommended - current
        
        if factor in recommendations:
            print(f'{factor:<30} | {current:+6.1%} | {recommended:+6.1%} | {change:+6.1%}')
        else:
            print(f'{factor:<30} | {current:+6.1%} | No data  | N/A')
    
    print('=' * 80)


if __name__ == '__main__':
    print('Analyzing historical bet performance to optimize adjustment weights...')
    print()
    
    try:
        compare_to_current_weights()
        
        print()
        print('=' * 80)
        print('SUMMARY')
        print('=' * 80)
        print()
        print('This analysis shows which factors actually predicted wins/losses.')
        print('Positive impact = factor increased win rate')
        print('Negative impact = factor decreased win rate')
        print()
        print('Recommended weights are based on:')
        print('  1. Observed impact on win rate')
        print('  2. Sample size (more data = more confidence)')
        print('  3. Capped at ±5% to prevent extreme adjustments')
        print()
        print('Next step: Update ml_model_streamlined.py with recommended weights')
        
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()
