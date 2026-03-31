#!/usr/bin/env python3
"""
Adjust bet stakes from $1.00 to $0.50 for specific dates
"""

import json
from pathlib import Path

def adjust_stakes():
    bet_results_path = Path("data/bet_results.json")
    
    # Load current data
    with open(bet_results_path, 'r') as f:
        data = json.load(f)
    
    print("Adjusting bets from $1.00 to $0.50 stakes")
    print("=" * 80)
    
    adjusted_count = 0
    
    for bet_id, result in data['results'].items():
        bet = result['bet']
        checked_at = result.get('checked_at', '')
        
        # Adjust March 7 and March 4 bets with $1.00 stakes
        if bet['stake'] == 1.00 and ('2026-03-07' in checked_at or '2026-03-04' in checked_at):
            old_stake = bet['stake']
            old_profit = result['profit']
            
            # Adjust stake to $0.50
            bet['stake'] = 0.50
            
            # Adjust profit (divide by 2)
            result['profit'] = old_profit / 2
            
            # Adjust EV if present
            if 'ev' in bet:
                bet['ev'] = bet['ev'] / 2
            
            print(f"{bet['pick']:30s} | {bet['game']:20s}")
            print(f"  Stake: ${old_stake:.2f} → ${bet['stake']:.2f}")
            print(f"  Profit: ${old_profit:+.2f} → ${result['profit']:+.2f}")
            print()
            
            adjusted_count += 1
    
    if adjusted_count > 0:
        # Save updated data
        with open(bet_results_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"✅ Adjusted {adjusted_count} bets")
        print(f"Saved to: {bet_results_path}")
    else:
        print("No bets to adjust")

if __name__ == "__main__":
    adjust_stakes()
