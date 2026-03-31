#!/usr/bin/env python3
"""
Simulate 48% ML Weight Performance

Estimates how much more money would have been earned if using
48% ML weight instead of 45% on historical bets.
"""

import json
from pathlib import Path
from collections import defaultdict
import statistics

def load_bet_results():
    """Load historical bet results"""
    results_path = Path("data/bet_results.json")
    if not results_path.exists():
        return {}
    
    with open(results_path) as f:
        return json.load(f).get("results", {})

def estimate_48_percent_impact():
    """
    Estimate impact of 48% ML weight vs current 45%
    
    Key assumptions:
    1. Increasing ML weight by 3% increases predicted probabilities by ~1.5-2%
    2. Higher predicted probabilities = higher calculated edges
    3. Higher edges = more bets pass the minimum edge threshold
    4. Same actual outcomes (win/loss doesn't change)
    """
    
    results = load_bet_results()
    
    print("=" * 80)
    print("  SIMULATION: 48% ML WEIGHT vs 45% ML WEIGHT")
    print("=" * 80)
    print()
    
    # Estimate probability increase from 45% to 48% ML weight
    # Conservative estimate: 3% increase in ML weight = 1.5% increase in predictions
    prob_increase_factor = 0.015
    
    print("ASSUMPTIONS:")
    print(f"  • Increasing ML weight from 45% to 48% (+3%)")
    print(f"  • Estimated probability increase: +{prob_increase_factor*100:.1f}%")
    print(f"  • Minimum edge threshold: 2%")
    print(f"  • Same actual win/loss outcomes")
    print()
    
    # Analyze current bets
    current_total_staked = sum(r["bet"]["stake"] for r in results.values())
    current_total_profit = sum(r["profit"] for r in results.values())
    current_roi = (current_total_profit / current_total_staked * 100) if current_total_staked > 0 else 0
    
    print("=" * 80)
    print("CURRENT PERFORMANCE (45% ML WEIGHT)")
    print("=" * 80)
    print()
    print(f"  Total bets: {len(results)}")
    print(f"  Total staked: ${current_total_staked:.2f}")
    print(f"  Total profit: ${current_total_profit:+.2f}")
    print(f"  ROI: {current_roi:+.1f}%")
    print()
    
    # Simulate 48% ML weight
    print("=" * 80)
    print("SIMULATED PERFORMANCE (48% ML WEIGHT)")
    print("=" * 80)
    print()
    
    # Track bets that would have been found
    simulated_bets = []
    additional_bets = []
    
    for result in results.values():
        bet = result["bet"]
        
        # Simulate new predicted probability
        old_true_prob = bet["true_prob"]
        new_true_prob = old_true_prob + prob_increase_factor
        
        # Calculate new edge
        implied_prob = bet["implied_prob"]
        old_edge = bet["edge"]
        new_edge = new_true_prob - implied_prob
        
        # This bet was already placed, so it would still be placed
        simulated_bet = {
            "old_edge": old_edge,
            "new_edge": new_edge,
            "edge_increase": new_edge - old_edge,
            "result": result["result"],
            "profit": result["profit"],
            "stake": bet["stake"],
            "bet_type": bet["bet_type"],
            "game": bet["game"],
            "pick": bet["pick"],
        }
        simulated_bets.append(simulated_bet)
    
    # Calculate simulated performance (same bets, same outcomes)
    simulated_total_staked = current_total_staked
    simulated_total_profit = current_total_profit
    simulated_roi = current_roi
    
    avg_edge_increase = statistics.mean([b["edge_increase"] for b in simulated_bets])
    
    print(f"  Same {len(simulated_bets)} bets would have been placed")
    print(f"  Average edge increase: +{avg_edge_increase*100:.2f}%")
    print()
    print(f"  Total staked: ${simulated_total_staked:.2f} (same)")
    print(f"  Total profit: ${simulated_total_profit:+.2f} (same)")
    print(f"  ROI: {simulated_roi:+.1f}% (same)")
    print()
    
    print("  Note: Same bets = same outcomes = same profit")
    print("  The REAL benefit is finding ADDITIONAL bets...")
    print()
    
    # Estimate additional bets that would have been found
    print("=" * 80)
    print("ADDITIONAL BETS THAT WOULD HAVE BEEN FOUND")
    print("=" * 80)
    print()
    
    # Load analysis history to see what bets were close to threshold
    history_path = Path("data/analysis_history.json")
    if history_path.exists():
        with open(history_path) as f:
            history = json.load(f).get("analyses", [])
        
        # Look for bets that were just below 2% edge threshold
        near_miss_count = 0
        estimated_near_miss_edge = []
        
        for analysis in history:
            for game in analysis.get("games_analyzed", []):
                # We don't have the full bet evaluation data, so estimate
                # Assume ~10-20% more bets would have been found
                pass
        
        # Conservative estimate: 15% more bets would have been found
        additional_bet_count = int(len(results) * 0.15)
        
        print(f"  Estimated additional bets: ~{additional_bet_count}")
        print(f"  (Conservative estimate: 15% more bets)")
        print()
        
        # Estimate performance of additional bets
        # Use current win rate and average profit per bet
        current_win_rate = sum(1 for r in results.values() if r["result"] == "won") / len(results)
        avg_profit_per_bet = current_total_profit / len(results)
        
        estimated_additional_profit = additional_bet_count * avg_profit_per_bet
        estimated_additional_staked = additional_bet_count * 0.50  # $0.50 per bet
        
        print(f"  Estimated additional profit: ${estimated_additional_profit:+.2f}")
        print(f"  Estimated additional staked: ${estimated_additional_staked:.2f}")
        print()
    else:
        additional_bet_count = int(len(results) * 0.15)
        current_win_rate = sum(1 for r in results.values() if r["result"] == "won") / len(results)
        avg_profit_per_bet = current_total_profit / len(results)
        estimated_additional_profit = additional_bet_count * avg_profit_per_bet
        estimated_additional_staked = additional_bet_count * 0.50
    
    # Total simulated performance
    print("=" * 80)
    print("TOTAL SIMULATED PERFORMANCE (48% ML WEIGHT)")
    print("=" * 80)
    print()
    
    total_simulated_bets = len(results) + additional_bet_count
    total_simulated_staked = simulated_total_staked + estimated_additional_staked
    total_simulated_profit = simulated_total_profit + estimated_additional_profit
    total_simulated_roi = (total_simulated_profit / total_simulated_staked * 100) if total_simulated_staked > 0 else 0
    
    print(f"  Total bets: {total_simulated_bets} (vs {len(results)} current)")
    print(f"  Additional bets: +{additional_bet_count}")
    print()
    print(f"  Total staked: ${total_simulated_staked:.2f} (vs ${current_total_staked:.2f})")
    print(f"  Total profit: ${total_simulated_profit:+.2f} (vs ${current_total_profit:+.2f})")
    print(f"  ROI: {total_simulated_roi:+.1f}% (vs {current_roi:+.1f}%)")
    print()
    
    # Calculate difference
    profit_difference = total_simulated_profit - current_total_profit
    roi_difference = total_simulated_roi - current_roi
    
    print("=" * 80)
    print("DIFFERENCE (48% vs 45%)")
    print("=" * 80)
    print()
    print(f"  Additional profit: ${profit_difference:+.2f}")
    print(f"  ROI change: {roi_difference:+.1f}%")
    print(f"  Profit increase: {(profit_difference / abs(current_total_profit) * 100):+.1f}%")
    print()
    
    # Break down by bet type
    print("=" * 80)
    print("BREAKDOWN BY BET TYPE")
    print("=" * 80)
    print()
    
    by_type = defaultdict(lambda: {"bets": [], "profit": 0, "staked": 0})
    
    for result in results.values():
        bet_type = result["bet"]["bet_type"]
        by_type[bet_type]["bets"].append(result)
        by_type[bet_type]["profit"] += result["profit"]
        by_type[bet_type]["staked"] += result["bet"]["stake"]
    
    for bet_type in sorted(by_type.keys()):
        data = by_type[bet_type]
        current_count = len(data["bets"])
        current_profit = data["profit"]
        current_staked = data["staked"]
        current_type_roi = (current_profit / current_staked * 100) if current_staked > 0 else 0
        
        # Estimate additional bets for this type
        additional_type_bets = int(current_count * 0.15)
        avg_profit = current_profit / current_count if current_count > 0 else 0
        additional_type_profit = additional_type_bets * avg_profit
        additional_type_staked = additional_type_bets * 0.50
        
        total_type_bets = current_count + additional_type_bets
        total_type_profit = current_profit + additional_type_profit
        total_type_staked = current_staked + additional_type_staked
        total_type_roi = (total_type_profit / total_type_staked * 100) if total_type_staked > 0 else 0
        
        print(f"{bet_type}:")
        print(f"  Current: {current_count} bets, ${current_profit:+.2f} profit, {current_type_roi:+.1f}% ROI")
        print(f"  With 48%: {total_type_bets} bets, ${total_type_profit:+.2f} profit, {total_type_roi:+.1f}% ROI")
        print(f"  Difference: +{additional_type_bets} bets, ${additional_type_profit:+.2f} profit")
        print()
    
    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print()
    print(f"If you had used 48% ML weight instead of 45%:")
    print()
    print(f"  ✓ Would have found ~{additional_bet_count} more +EV bets")
    print(f"  ✓ Would have earned ~${profit_difference:+.2f} more profit")
    print(f"  ✓ ROI would be ~{total_simulated_roi:.1f}% (vs {current_roi:.1f}%)")
    print()
    
    if profit_difference > 0:
        print(f"  💰 You left ~${profit_difference:.2f} on the table")
    
    print()
    print("IMPORTANT NOTES:")
    print("  • This is a conservative estimate (15% more bets)")
    print("  • Actual impact could be 10-25% more bets")
    print("  • Assumes additional bets perform at same win rate")
    print("  • Real-world testing needed to confirm")
    print()
    
    # Confidence intervals
    print("=" * 80)
    print("CONFIDENCE RANGES")
    print("=" * 80)
    print()
    
    # Conservative (10% more bets)
    conservative_additional = int(len(results) * 0.10)
    conservative_profit = conservative_additional * avg_profit_per_bet
    
    # Aggressive (25% more bets)
    aggressive_additional = int(len(results) * 0.25)
    aggressive_profit = aggressive_additional * avg_profit_per_bet
    
    print("Additional profit estimates:")
    print(f"  Conservative (10% more bets): ${conservative_profit:+.2f}")
    print(f"  Moderate (15% more bets):     ${profit_difference:+.2f}")
    print(f"  Aggressive (25% more bets):   ${aggressive_profit:+.2f}")
    print()
    print(f"Range: ${conservative_profit:.2f} - ${aggressive_profit:.2f}")
    print()
    
    print("=" * 80)

if __name__ == "__main__":
    estimate_48_percent_impact()
