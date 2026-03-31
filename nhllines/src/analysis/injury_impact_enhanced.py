"""
Enhanced Injury Impact Calculator
==================================
Uses historical data analysis to calculate injury impact on win probability.
"""

import json
from pathlib import Path
from src.analysis.injury_tracker import calculate_injury_impact


def load_injury_coefficients():
    """Load injury impact coefficients from historical analysis."""
    coef_path = Path(__file__).parent.parent.parent / "data" / "injury_coefficients.json"
    
    if coef_path.exists():
        with open(coef_path, 'r') as f:
            return json.load(f)
    
    # Default coefficients if file doesn't exist
    return {
        'injury_win_prob_coefficient': -0.02,
        'position_multipliers': {
            'G': 1.5,
            'D': 1.2,
            'F': 1.0
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
        }
    }


def calculate_injury_win_prob_adjustment(home_injuries: list, away_injuries: list, 
                                         home_team: str, away_team: str) -> dict:
    """
    Calculate win probability adjustment based on injuries.
    
    Args:
        home_injuries: List of home team injuries
        away_injuries: List of away team injuries
        home_team: Home team abbreviation
        away_team: Away team abbreviation
    
    Returns:
        dict with:
        - home_win_prob_adjustment: float (-0.20 to +0.20)
        - home_injury_impact: float (0-10)
        - away_injury_impact: float (0-10)
        - net_impact: float (negative = home disadvantaged)
        - explanation: str
    """
    # Load coefficients
    coefficients = load_injury_coefficients()
    coef = coefficients['injury_win_prob_coefficient']
    
    # Calculate injury impacts
    home_impact = calculate_injury_impact(home_injuries, home_team)
    away_impact = calculate_injury_impact(away_injuries, away_team)
    
    home_score = home_impact['impact_score']
    away_score = away_impact['impact_score']
    
    # Net impact (positive = home more injured)
    net_impact = home_score - away_score

    # Win probability adjustment
    # Negative net_impact = home team less injured = positive adjustment
    # Scale coefficient for new wider range (0-30+ instead of 0-10)
    # Divide by 3 to keep adjustments proportional to old behavior
    scaled_coef = coef / 3.0
    win_prob_adjustment = -net_impact * scaled_coef

    # Cap adjustment at ±20%
    win_prob_adjustment = max(-0.20, min(0.20, win_prob_adjustment))

    # Generate explanation (thresholds adjusted for new 0-30+ scale)
    if abs(net_impact) < 3:
        explanation = "Injuries roughly equal"
    elif net_impact > 8:
        explanation = f"{home_team} significantly more injured (-{abs(win_prob_adjustment):.1%})"
    elif net_impact < -8:
        explanation = f"{away_team} significantly more injured (+{abs(win_prob_adjustment):.1%})"
    elif net_impact > 0:
        explanation = f"{home_team} more injured ({win_prob_adjustment:+.1%})"
    else:
        explanation = f"{away_team} more injured ({win_prob_adjustment:+.1%})"
    
    return {
        'home_win_prob_adjustment': win_prob_adjustment,
        'home_injury_impact': home_score,
        'away_injury_impact': away_score,
        'net_impact': net_impact,
        'explanation': explanation,
        'home_key_injuries': home_impact['key_injuries'],
        'away_key_injuries': away_impact['key_injuries'],
    }


def get_injury_adjusted_probabilities(base_home_prob: float, home_injuries: list, 
                                     away_injuries: list, home_team: str, 
                                     away_team: str) -> dict:
    """
    Adjust win probabilities based on injury impact.
    
    Args:
        base_home_prob: Base home win probability (0-1)
        home_injuries: List of home team injuries
        away_injuries: List of away team injuries
        home_team: Home team abbreviation
        away_team: Away team abbreviation
    
    Returns:
        dict with adjusted probabilities and explanation
    """
    adjustment = calculate_injury_win_prob_adjustment(
        home_injuries, away_injuries, home_team, away_team
    )
    
    # Apply adjustment
    adjusted_home_prob = base_home_prob + adjustment['home_win_prob_adjustment']
    
    # Ensure probabilities stay in valid range
    adjusted_home_prob = max(0.05, min(0.95, adjusted_home_prob))
    adjusted_away_prob = 1 - adjusted_home_prob
    
    return {
        'adjusted_home_prob': adjusted_home_prob,
        'adjusted_away_prob': adjusted_away_prob,
        'adjustment': adjustment['home_win_prob_adjustment'],
        'explanation': adjustment['explanation'],
        'home_injury_impact': adjustment['home_injury_impact'],
        'away_injury_impact': adjustment['away_injury_impact'],
        'home_key_injuries': adjustment['home_key_injuries'],
        'away_key_injuries': adjustment['away_key_injuries'],
    }


if __name__ == "__main__":
    # Test the injury impact calculator
    print("=" * 80)
    print("  INJURY IMPACT CALCULATOR TEST")
    print("=" * 80)
    print()
    
    from src.analysis.injury_tracker import get_todays_injuries
    
    # Get current injuries
    all_injuries = get_todays_injuries()
    
    # Find two teams with different injury levels
    teams_with_injuries = [(t, len(inj)) for t, inj in all_injuries.items() if inj]
    teams_with_injuries.sort(key=lambda x: x[1], reverse=True)
    
    if len(teams_with_injuries) >= 2:
        # Most injured team vs. least injured team
        most_injured = teams_with_injuries[0][0]
        least_injured = teams_with_injuries[-1][0]
        
        print(f"Test Game: {least_injured} @ {most_injured}")
        print()
        
        # Calculate adjustment
        result = get_injury_adjusted_probabilities(
            base_home_prob=0.55,  # Slight home advantage
            home_injuries=all_injuries[most_injured],
            away_injuries=all_injuries[least_injured],
            home_team=most_injured,
            away_team=least_injured
        )
        
        print(f"Base Home Win Probability: 55.0%")
        print(f"Adjusted Home Win Probability: {result['adjusted_home_prob']:.1%}")
        print(f"Adjustment: {result['adjustment']:+.1%}")
        print()
        print(f"Explanation: {result['explanation']}")
        print()
        print(f"Home Team ({most_injured}) Injury Impact: {result['home_injury_impact']:.1f}/10")
        if result['home_key_injuries']:
            print(f"  Key injuries:")
            for inj in result['home_key_injuries']:
                print(f"    - {inj['player']} ({inj['position']}) - {inj['status']}")
        
        print()
        print(f"Away Team ({least_injured}) Injury Impact: {result['away_injury_impact']:.1f}/10")
        if result['away_key_injuries']:
            print(f"  Key injuries:")
            for inj in result['away_key_injuries']:
                print(f"    - {inj['player']} ({inj['position']}) - {inj['status']}")
    else:
        print("Not enough teams with injuries for testing")
