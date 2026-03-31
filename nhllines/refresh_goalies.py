#!/usr/bin/env python3
"""
Refresh Goalie Starters
=======================
Updates goalie starter information closer to game time.
Run this 1-2 hours before games start for confirmed starters.

Usage:
    python refresh_goalies.py
"""

import json
from pathlib import Path
from datetime import datetime
from src.analysis.goalie_tracker import get_todays_starters

def refresh_goalies():
    """Refresh goalie starter data and update analysis."""
    print("=" * 60)
    print("  Refreshing Goalie Starters")
    print(f"  {datetime.now().strftime('%A, %B %d %Y %H:%M')}")
    print("=" * 60)
    print()
    
    # Clear goalie cache to force fresh fetch
    cache_dir = Path(__file__).parent / "cache"
    goalie_cache_files = list(cache_dir.glob("dailyfaceoff_goalies_*.json"))
    
    if goalie_cache_files:
        print(f"Clearing {len(goalie_cache_files)} cached goalie file(s)...")
        for cache_file in goalie_cache_files:
            cache_file.unlink()
            print(f"  Removed: {cache_file.name}")
    
    # Fetch fresh goalie data
    print("\nFetching fresh goalie data...")
    starters = get_todays_starters()
    
    print(f"\n✅ Updated goalie data for {len(starters)} teams")
    print()
    
    # Show confirmed vs projected
    confirmed = []
    projected = []
    
    for team, data in starters.items():
        starter = data.get('starter')
        if starter:
            status = starter.get('status', 'projected')
            if status == 'confirmed':
                confirmed.append((team, starter['name']))
            else:
                projected.append((team, starter['name']))
    
    if confirmed:
        print(f"Confirmed Starters ({len(confirmed)}):")
        for team, name in sorted(confirmed):
            print(f"  ✓ {team}: {name}")
    
    if projected:
        print(f"\nProjected Starters ({len(projected)}):")
        for team, name in sorted(projected):
            print(f"  ? {team}: {name}")
    
    if not confirmed and not projected:
        print("No starter information available yet.")
        print("Try running closer to game time (1-2 hours before).")
    
    print()
    print("=" * 60)
    print("  Next: Re-run analysis to use updated goalie data")
    print("  python main.py --conservative")
    print("=" * 60)


if __name__ == "__main__":
    refresh_goalies()
