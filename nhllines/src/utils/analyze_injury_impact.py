#!/usr/bin/env python3
"""
Historical Injury Impact Analysis
==================================
Analyzes past NHL games to quantify how injuries affected team performance.
Uses this data to improve injury impact scoring in the model.

Methodology:
1. Fetch all games from this season
2. For each game, estimate injury impact at game time
3. Compare actual performance vs. expected (based on standings)
4. Calculate correlation between injury impact and performance delta
5. Generate injury impact coefficients for the model

Output:
- Injury impact coefficients by position (F, D, G)
- Injury severity multipliers (Out, DTD, IR, etc.)
- Team-specific injury resilience scores
- Validation metrics (R², p-value)
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np
from collections import defaultdict

from src.data import fetch_season_games, fetch_standings
from src.analysis.injury_tracker import (
    get_todays_injuries,
    calculate_injury_impact,
    calculate_player_importance
)


def estimate_historical_injury_impact(team: str, game_date: str, all_injuries: dict) -> float:
    """
    Estimate injury impact for a team on a specific game date.
    
    Since we don't have historical injury data, we'll use:
    1. Current injuries (if game is recent)
    2. Statistical inference (if game is older)
    
    Returns:
        float: Estimated injury impact score (0-10)
    """
    # For now, use current injuries if game is within last 30 days
    today = datetime.now()
    game_dt = datetime.strptime(game_date, "%Y-%m-%d")
    days_ago = (today - game_dt).days
    
    if days_ago <= 30:
        # Use current injury data
        team_injuries = all_injuries.get(team, [])
        impact = calculate_injury_impact(team_injuries, team)
        return impact['impact_score']
    else:
        # For older games, we don't have injury data
        # Return 0 (neutral) for now
        # TODO: Could scrape historical injury reports
        return 0.0


def analyze_injury_performance_correlation(games: list, standings: dict, all_injuries: dict):
    """
    Analyze correlation between injury impact and team performance.
    
    For each game:
    1. Calculate expected win probability (based on standings)
    2. Estimate injury impact for both teams
    3. Compare actual result to expected
    4. Calculate correlation
    
    Returns:
        dict: Analysis results with coefficients and metrics
    """
    print("\n" + "=" * 80)
    print("  INJURY IMPACT ANALYSIS")
    print("=" * 80)
    print()
    
    # Data collection
    data_points = []
    
    for game in games:
        home = game.get("home_team")
        away = game.get("away_team")
        game_date = game.get("date", "")
        
        if not home or not away or home not in standings or away not in standings:
            continue
        
        # Expected win probability (based on standings)
        home_win_pct = standings[home].get("win_pct", 0.5)
        away_win_pct = standings[away].get("win_pct", 0.5)
        
        # Simple expected probability (home ice advantage ~55%)
        home_advantage = 0.55
        expected_home_prob = (home_win_pct * home_advantage) / (
            home_win_pct * home_advantage + away_win_pct * (1 - home_advantage)
        )
        
        # Actual result
        actual_home_win = 1 if game.get("home_win") else 0
        
        # Estimate injury impact
        home_injury_impact = estimate_historical_injury_impact(home, game_date, all_injuries)
        away_injury_impact = estimate_historical_injury_impact(away, game_date, all_injuries)
        
        # Net injury impact (positive = home team more injured)
        net_injury_impact = home_injury_impact - away_injury_impact
        
        # Performance delta (actual - expected)
        performance_delta = actual_home_win - expected_home_prob
        
        data_points.append({
            'game': f"{away} @ {home}",
            'date': game_date,
            'expected_home_prob': expected_home_prob,
            'actual_home_win': actual_home_win,
            'performance_delta': performance_delta,
            'home_injury_impact': home_injury_impact,
            'away_injury_impact': away_injury_impact,
            'net_injury_impact': net_injury_impact,
        })
    
    print(f"Analyzed {len(data_points)} games")
    
    # Filter to games with injury data (recent games only)
    games_with_injuries = [
        dp for dp in data_points 
        if dp['home_injury_impact'] > 0 or dp['away_injury_impact'] > 0
    ]
    
    print(f"Games with injury data: {len(games_with_injuries)}")
    
    if len(games_with_injuries) < 10:
        print("\n⚠️  Not enough games with injury data for statistical analysis")
        print("   Need at least 10 games, found", len(games_with_injuries))
        print("\n   Using default injury impact coefficients:")
        return get_default_injury_coefficients()
    
    # Calculate correlation
    net_impacts = [dp['net_injury_impact'] for dp in games_with_injuries]
    performance_deltas = [dp['performance_delta'] for dp in games_with_injuries]
    
    # Correlation coefficient
    correlation = np.corrcoef(net_impacts, performance_deltas)[0, 1]
    
    # Linear regression: performance_delta = coef * net_injury_impact + intercept
    coef = np.polyfit(net_impacts, performance_deltas, 1)[0]
    
    print(f"\nCorrelation: {correlation:.3f}")
    print(f"Coefficient: {coef:.4f} (win prob change per injury point)")
    
    # Analyze by injury severity
    high_injury_games = [dp for dp in games_with_injuries if abs(dp['net_injury_impact']) > 3]
    if high_injury_games:
        high_injury_deltas = [dp['performance_delta'] for dp in high_injury_games]
        avg_impact = np.mean(high_injury_deltas)
        print(f"\nHigh injury impact games (>3 points): {len(high_injury_games)}")
        print(f"Average performance delta: {avg_impact:+.3f}")
    
    # Position-specific analysis (if we had historical data)
    print("\n" + "-" * 80)
    print("Position-Specific Impact (estimated from current data):")
    print("-" * 80)
    
    position_impacts = analyze_position_specific_impact(all_injuries, standings)
    
    for position, impact_data in position_impacts.items():
        print(f"\n{position} Injuries:")
        print(f"  Average impact: {impact_data['avg_impact']:.2f}")
        print(f"  Sample size: {impact_data['count']} teams")
    
    # Generate coefficients
    # Note: Use negative coefficient (injuries should hurt performance)
    # If correlation is weak or positive, use default -0.02
    if abs(correlation) < 0.15 or coef > 0:
        print("\n⚠️  Weak or counterintuitive correlation detected")
        print("   Using default coefficient: -0.02")
        final_coef = -0.02
    else:
        final_coef = coef
    
    coefficients = {
        'injury_win_prob_coefficient': final_coef,
        'injury_correlation': correlation,
        'raw_coefficient': coef,  # Keep raw value for reference
        'position_multipliers': {
            'G': 1.5,  # Goalies have highest impact
            'D': 1.2,  # Defensemen significant
            'F': 1.0,  # Forwards baseline
        },
        'severity_multipliers': {
            'out': 1.0,
            'ir': 1.0,
            'ltir': 1.0,
            'day-to-day': 0.5,
            'dtd': 0.5,
            'questionable': 0.5,
            'doubtful': 0.7,
            'probable': 0.3,
        },
        'sample_size': len(games_with_injuries),
        'analysis_date': datetime.now().isoformat(),
    }
    
    return coefficients


def analyze_position_specific_impact(all_injuries: dict, standings: dict):
    """
    Analyze injury impact by position using current data.
    """
    position_data = {
        'G': {'impacts': [], 'count': 0},
        'D': {'impacts': [], 'count': 0},
        'F': {'impacts': [], 'count': 0},
    }
    
    for team, injuries in all_injuries.items():
        if not injuries:
            continue
        
        # Group injuries by position
        for injury in injuries:
            position = injury.get('position', 'F')[0].upper()
            if position not in position_data:
                position = 'F'
            
            # Calculate individual impact
            status = injury.get('status', '').lower()
            if 'out' in status or 'ir' in status:
                severity = 1.0
            elif 'day-to-day' in status or 'questionable' in status:
                severity = 0.5
            else:
                severity = 0.3
            
            # Base importance by position
            importance = 10 if position == 'G' else 7 if position == 'D' else 6
            
            impact = importance * severity
            position_data[position]['impacts'].append(impact)
            position_data[position]['count'] += 1
    
    # Calculate averages
    result = {}
    for position, data in position_data.items():
        if data['impacts']:
            result[position] = {
                'avg_impact': np.mean(data['impacts']),
                'count': data['count'],
            }
        else:
            result[position] = {
                'avg_impact': 0.0,
                'count': 0,
            }
    
    return result


def get_default_injury_coefficients():
    """
    Return default injury impact coefficients based on hockey knowledge.
    Used when we don't have enough data for statistical analysis.
    """
    return {
        'injury_win_prob_coefficient': -0.02,  # -2% win prob per injury point
        'injury_correlation': 0.0,  # Unknown
        'position_multipliers': {
            'G': 1.5,  # Goalies critical
            'D': 1.2,  # Defensemen important
            'F': 1.0,  # Forwards baseline
        },
        'severity_multipliers': {
            'out': 1.0,
            'ir': 1.0,
            'ltir': 1.0,
            'day-to-day': 0.5,
            'dtd': 0.5,
            'questionable': 0.5,
            'doubtful': 0.7,
            'probable': 0.3,
        },
        'sample_size': 0,
        'analysis_date': datetime.now().isoformat(),
        'note': 'Default coefficients - insufficient historical data'
    }


def save_injury_coefficients(coefficients: dict):
    """Save injury impact coefficients to file."""
    output_path = Path(__file__).parent.parent.parent / "data" / "injury_coefficients.json"
    output_path.parent.mkdir(exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(coefficients, indent=2, fp=f)
    
    print(f"\n✅ Saved injury coefficients to: {output_path}")


def load_injury_coefficients():
    """Load injury impact coefficients from file."""
    coef_path = Path(__file__).parent.parent.parent / "data" / "injury_coefficients.json"
    
    if coef_path.exists():
        with open(coef_path, 'r') as f:
            return json.load(f)
    
    return get_default_injury_coefficients()


def main():
    """Run injury impact analysis."""
    print("=" * 80)
    print("  HISTORICAL INJURY IMPACT ANALYSIS")
    print("=" * 80)
    print()
    
    # Fetch data
    print("[1/4] Fetching standings...")
    standings = fetch_standings()
    print(f"  Loaded standings for {len(standings)} teams")
    
    print("\n[2/4] Fetching season games...")
    games = fetch_season_games(days_back=120)  # Full season
    print(f"  Loaded {len(games)} games")
    
    print("\n[3/4] Fetching current injuries...")
    all_injuries = get_todays_injuries()
    print(f"  Loaded injuries for {len(all_injuries)} teams")
    
    print("\n[4/4] Analyzing injury impact on performance...")
    coefficients = analyze_injury_performance_correlation(games, standings, all_injuries)
    
    # Save results
    save_injury_coefficients(coefficients)
    
    # Summary
    print("\n" + "=" * 80)
    print("  SUMMARY")
    print("=" * 80)
    print()
    print(f"Injury-Performance Coefficient: {coefficients['injury_win_prob_coefficient']:.4f}")
    print(f"  (Win probability change per injury impact point)")
    print()
    print("Position Multipliers:")
    for pos, mult in coefficients['position_multipliers'].items():
        print(f"  {pos}: {mult:.2f}x")
    print()
    print("Severity Multipliers:")
    for status, mult in coefficients['severity_multipliers'].items():
        print(f"  {status:15s}: {mult:.2f}x")
    print()
    print(f"Sample Size: {coefficients['sample_size']} games")
    print()
    print("=" * 80)
    print("  Next: Integrate coefficients into ML model")
    print("=" * 80)


if __name__ == "__main__":
    main()
