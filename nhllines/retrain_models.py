#!/usr/bin/env python3
"""
Retrain ML Models with Latest Data
===================================
Run this to update the ML models with the most recent game data.
"""

import os
from pathlib import Path
from src.data import fetch_standings, fetch_season_games, get_team_recent_form
from src.models import StreamlinedNHLMLModel

def retrain_models(days_back=90):
    """Retrain ML models with latest historical data."""
    print("=" * 60)
    print("  Retraining ML Models with Latest Data")
    print("=" * 60)
    print()
    
    # Fetch latest data
    print(f"[1/4] Fetching standings...")
    standings = fetch_standings()
    print(f"  Loaded standings for {len(standings)} teams")
    
    print(f"\n[2/4] Fetching last {days_back} days of games...")
    all_games = fetch_season_games(days_back=days_back)
    print(f"  Loaded {len(all_games)} completed games")
    
    print(f"\n[3/4] Calculating team form...")
    team_forms = {}
    for team in standings:
        team_forms[team] = get_team_recent_form(team, all_games, n=10)
    print(f"  Calculated form for {len(team_forms)} teams")
    
    # Delete old models
    print(f"\n[4/4] Training new models...")
    model_path = Path(__file__).parent / "ml_models"
    for model_file in model_path.glob("*.pkl"):
        print(f"  Removing old model: {model_file.name}")
        model_file.unlink()
    
    # Train new models
    ml_model = StreamlinedNHLMLModel()
    success = ml_model.train(all_games, standings, team_forms)
    
    if success:
        print("\n✅ Models retrained successfully!")
        print(f"   Training data: {len(all_games)} games")
        print(f"   Models saved to: {model_path}")
    else:
        print("\n❌ Model training failed")
        return False
    
    print("\n" + "=" * 60)
    print("  Next: Run 'python main.py --conservative' to use new models")
    print("=" * 60)
    
    return True

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Retrain ML models")
    parser.add_argument("--days", type=int, default=90,
                       help="Days of historical data to use (default: 90)")
    args = parser.parse_args()
    
    retrain_models(days_back=args.days)
