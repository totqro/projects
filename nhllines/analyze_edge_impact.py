#!/usr/bin/env python3
"""
Analyze Edge Impact of Changing ML Weight

Determines whether increasing ML weight would increase or decrease
the calculated edge on bets.
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

def analyze_edge_vs_outcome():
    """
    Analyze relationship between calculated edge and actual outcomes
    
    Key insight: If model is underconfident, increasing ML weight would:
    - INCREASE predicted probabilities
    - INCREASE calculated edge (if odds stay same)
    - Potentially find MORE +EV bets
    """
    
    results = load_bet_results()
    
    print("=" * 80)
    print("  EDGE IMPACT ANALYSIS")
    print("=" * 80)
    print()
    
    print("Understanding the relationship between ML weight and edge:")
    print()
    print("  Edge = True Probability - Implied Probability")
    print()
    print("  If we INCREASE ML weight:")
    print("    → True probability predictions will INCREASE (ML is more confident)")
    print("    → Implied probability stays same (market odds don't change)")
    print("    → Therefore: Edge will INCREASE")
    print()
    print("  If we DECREASE ML weight:")
    print("    → True probability predictions will DECREASE")
    print("    → Edge will DECREASE")
    print()
    
    print("=" * 80)
    print("CURRENT SITUATION ANALYSIS")
    print("=" * 80)
    print()
    
    # Analyze by bet type
    by_type = defaultdict(lambda: {
        "bets": [],
        "won": 0,
        "total": 0,
        "avg_true_prob": [],
        "avg_implied_prob": [],
        "avg_edge": [],
        "actual_wr": 0
    })
    
    for result in results.values():
        bet_type = result["bet"]["bet_type"]
        by_type[bet_type]["bets"].append(result)
        by_type[bet_type]["total"] += 1
        by_type[bet_type]["avg_true_prob"].append(result["bet"]["true_prob"])
        by_type[bet_type]["avg_implied_prob"].append(result["bet"]["implied_prob"])
        by_type[bet_type]["avg_edge"].append(result["bet"]["edge"])
        if result["result"] == "won":
            by_type[bet_type]["won"] += 1
    
    for bet_type in sorted(by_type.keys()):
        data = by_type[bet_type]
        data["actual_wr"] = data["won"] / data["total"]
        
        avg_true = statistics.mean(data["avg_true_prob"])
        avg_implied = statistics.mean(data["avg_implied_prob"])
        avg_edge = statistics.mean(data["avg_edge"])
        actual_wr = data["actual_wr"]
        
        print(f"{bet_type}:")
        print(f"  Current avg true prob: {avg_true:.1%}")
        print(f"  Actual win rate: {actual_wr:.1%}")
        print(f"  Underconfidence: {actual_wr - avg_true:+.1%}")
        print(f"  Current avg edge: {avg_edge:.1%}")
        print()
        
        # Calculate what edge would be if we were perfectly calibrated
        calibrated_edge = actual_wr - avg_implied
        edge_increase = calibrated_edge - avg_edge
        
        print(f"  If perfectly calibrated:")
        print(f"    True prob would be: {actual_wr:.1%} (actual WR)")
        print(f"    Edge would be: {calibrated_edge:.1%}")
        print(f"    Edge increase: {edge_increase:+.1%}")
        print()
        
        # Estimate impact of increasing ML weight
        # Rough estimate: increasing ML weight by 5% might increase predictions by 2-3%
        estimated_prob_increase = 0.025  # Conservative estimate
        new_true_prob = avg_true + estimated_prob_increase
        new_edge = new_true_prob - avg_implied
        
        print(f"  If we increase ML weight to 50% (estimated):")
        print(f"    True prob might increase to: {new_true_prob:.1%}")
        print(f"    New edge would be: {new_edge:.1%}")
        print(f"    Edge change: {new_edge - avg_edge:+.1%}")
        print()
        
        # Key insight
        if actual_wr > avg_true:
            print(f"  ✓ INCREASING ML weight would INCREASE edge")
            print(f"    → Model is underconfident, needs to be more aggressive")
            print(f"    → Higher edges = more +EV bets found")
        else:
            print(f"  ⚠ INCREASING ML weight would DECREASE edge")
            print(f"    → Model is overconfident, needs to be more conservative")
            print(f"    → Lower edges = fewer but better quality bets")
        print()
        print("-" * 80)
        print()
    
    # Overall analysis
    print("=" * 80)
    print("OVERALL IMPACT ASSESSMENT")
    print("=" * 80)
    print()
    
    total_won = sum(r["result"] == "won" for r in results.values())
    total_bets = len(results)
    overall_wr = total_won / total_bets
    
    avg_true_prob = statistics.mean([r["bet"]["true_prob"] for r in results.values()])
    avg_implied_prob = statistics.mean([r["bet"]["implied_prob"] for r in results.values()])
    avg_edge = statistics.mean([r["bet"]["edge"] for r in results.values()])
    
    underconfidence = overall_wr - avg_true_prob
    
    print(f"Current Performance:")
    print(f"  Actual win rate: {overall_wr:.1%}")
    print(f"  Avg predicted prob: {avg_true_prob:.1%}")
    print(f"  Underconfidence: {underconfidence:+.1%}")
    print(f"  Avg edge: {avg_edge:.1%}")
    print()
    
    if underconfidence > 0.05:
        print("RECOMMENDATION: INCREASE ML WEIGHT")
        print()
        print("Why this INCREASES edge:")
        print("  1. Model is underconfident (predicting lower than actual)")
        print("  2. Increasing ML weight → higher predicted probabilities")
        print("  3. Higher predictions → larger edge (vs same market odds)")
        print("  4. Larger edge → more +EV bets identified")
        print()
        print("Expected outcomes:")
        print("  ✓ More bets found (higher edges)")
        print("  ✓ Better calibration (predictions match reality)")
        print("  ✓ Higher ROI (betting on more true edges)")
        print()
        print("Risk:")
        print("  ⚠ If we increase too much, could become overconfident")
        print("  → Suggest testing 48% first (small increase)")
        print()
    elif underconfidence < -0.05:
        print("RECOMMENDATION: DECREASE ML WEIGHT")
        print()
        print("Why this INCREASES true edge:")
        print("  1. Model is overconfident (predicting higher than actual)")
        print("  2. Decreasing ML weight → lower predicted probabilities")
        print("  3. Lower predictions → smaller calculated edge")
        print("  4. BUT: Better calibration → betting on REAL edges")
        print()
        print("Expected outcomes:")
        print("  ✓ Fewer bets found (more selective)")
        print("  ✓ Better calibration (predictions match reality)")
        print("  ✓ Higher quality bets (real edges, not phantom edges)")
        print()
    else:
        print("RECOMMENDATION: MAINTAIN CURRENT WEIGHT")
        print()
        print("Model is well-calibrated:")
        print("  ✓ Predictions match actual outcomes")
        print("  ✓ Calculated edges are real")
        print("  ✓ No adjustment needed")
        print()
    
    print("=" * 80)
    print("KEY INSIGHT: EDGE vs TRUE EDGE")
    print("=" * 80)
    print()
    print("There are two types of edge:")
    print()
    print("1. CALCULATED EDGE (what model shows)")
    print("   = Model's predicted probability - Market's implied probability")
    print()
    print("2. TRUE EDGE (reality)")
    print("   = Actual win probability - Market's implied probability")
    print()
    print("If model is UNDERCONFIDENT:")
    print("  → Calculated edge is LOWER than true edge")
    print("  → We're missing +EV bets (false negatives)")
    print("  → Increasing ML weight INCREASES calculated edge")
    print("  → This brings calculated edge CLOSER to true edge")
    print("  → Result: Find more REAL +EV bets")
    print()
    print("If model is OVERCONFIDENT:")
    print("  → Calculated edge is HIGHER than true edge")
    print("  → We're betting on phantom edges (false positives)")
    print("  → Decreasing ML weight DECREASES calculated edge")
    print("  → This brings calculated edge CLOSER to true edge")
    print("  → Result: Avoid bad bets, improve quality")
    print()
    
    print("=" * 80)
    print("BOTTOM LINE")
    print("=" * 80)
    print()
    
    if underconfidence > 0.05:
        print("Your model is UNDERCONFIDENT.")
        print()
        print("Increasing ML weight will:")
        print("  ✓ INCREASE calculated edge")
        print("  ✓ Find MORE +EV bets")
        print("  ✓ Improve calibration")
        print("  ✓ Capture more TRUE edge")
        print()
        print("This is GOOD - you're currently leaving money on the table.")
        print()
        print("Recommended action:")
        print("  → Test 48% ML weight for next 50 bets")
        print("  → Compare results to current 45%")
        print("  → If performance improves, consider 50%")
    else:
        print("Your model is well-calibrated or overconfident.")
        print("Maintain or decrease ML weight as appropriate.")
    
    print()
    print("=" * 80)

if __name__ == "__main__":
    analyze_edge_vs_outcome()
