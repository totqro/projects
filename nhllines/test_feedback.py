#!/usr/bin/env python3
"""
Test the model feedback system with sample data.
"""

import json
from pathlib import Path
from src.analysis.model_feedback import ModelFeedback

def create_sample_results():
    """Create sample bet results for testing."""
    return {
        "bet_1": {
            "bet": {
                "game": "TOR @ BOS",
                "pick": "TOR ML",
                "odds": 150,
                "stake": 1.0,
                "true_prob": 0.55,
                "confidence": 0.65,
                "edge": 0.04,
                "bet_type": "Moneyline",
                "ev": 0.04
            },
            "result": "won",
            "profit": 1.50,
            "checked_at": "2026-04-01T10:00:00"
        },
        "bet_2": {
            "bet": {
                "game": "NYR @ PHI",
                "pick": "Over 6.5",
                "odds": -110,
                "stake": 1.0,
                "true_prob": 0.52,
                "confidence": 0.58,
                "edge": 0.025,
                "bet_type": "Total",
                "ev": 0.025
            },
            "result": "lost",
            "profit": -1.0,
            "checked_at": "2026-04-01T10:00:00"
        },
        "bet_3": {
            "bet": {
                "game": "COL @ VGK",
                "pick": "COL ML",
                "odds": 120,
                "stake": 1.0,
                "true_prob": 0.60,
                "confidence": 0.72,
                "edge": 0.055,
                "bet_type": "Moneyline",
                "ev": 0.055
            },
            "result": "won",
            "profit": 1.20,
            "checked_at": "2026-04-01T10:00:00"
        },
        "bet_4": {
            "bet": {
                "game": "EDM @ CGY",
                "pick": "Under 6.0",
                "odds": -105,
                "stake": 1.0,
                "true_prob": 0.51,
                "confidence": 0.55,
                "edge": 0.022,
                "bet_type": "Total",
                "ev": 0.022
            },
            "result": "won",
            "profit": 0.95,
            "checked_at": "2026-04-01T10:00:00"
        },
        "bet_5": {
            "bet": {
                "game": "TB @ FLA",
                "pick": "FLA ML",
                "odds": -150,
                "stake": 1.0,
                "true_prob": 0.65,
                "confidence": 0.70,
                "edge": 0.05,
                "bet_type": "Moneyline",
                "ev": 0.05
            },
            "result": "lost",
            "profit": -1.0,
            "checked_at": "2026-04-01T10:00:00"
        }
    }

def test_feedback_system():
    """Test the feedback system with sample data."""
    print("=" * 60)
    print("  Testing Model Feedback System")
    print("=" * 60)
    print()
    
    # Create feedback instance
    feedback = ModelFeedback()
    
    # Create sample results
    sample_results = create_sample_results()
    
    print(f"Testing with {len(sample_results)} sample bets...")
    print()
    
    # Update feedback
    feedback.update_from_results(sample_results)
    
    # Test optimal weight retrieval
    optimal_weight = feedback.get_optimal_model_weight()
    print(f"\n✅ Optimal model weight: {optimal_weight:.2f}")
    
    # Test confidence adjustment
    test_confidences = [0.50, 0.65, 0.80, 0.95]
    print("\n✅ Confidence adjustments:")
    for conf in test_confidences:
        adjusted = feedback.get_adjusted_confidence(conf)
        print(f"   {conf:.2f} -> {adjusted:.2f}")
    
    # Test bet filtering
    print("\n✅ Bet filtering:")
    test_bets = [
        (0.04, 0.65, "Moneyline"),
        (0.02, 0.50, "Total"),
        (0.06, 0.75, "Moneyline"),
    ]
    for edge, conf, bet_type in test_bets:
        should_take = feedback.should_take_bet(edge, conf, bet_type)
        status = "✓ TAKE" if should_take else "✗ SKIP"
        print(f"   {status}: {bet_type} edge={edge:.1%} conf={conf:.0%}")
    
    print("\n" + "=" * 60)
    print("  Test Complete!")
    print("=" * 60)

if __name__ == "__main__":
    test_feedback_system()
