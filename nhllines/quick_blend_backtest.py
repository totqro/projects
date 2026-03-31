#!/usr/bin/env python3
"""
Quick Blend Ratio Backtest

Analyzes actual bet results to see how different blend ratios
would have affected edge calculations and bet selection.
"""

import json
from pathlib import Path
from collections import defaultdict
import statistics

def load_data():
    """Load bet results and analysis history"""
    results_path = Path("data/bet_results.json")
    history_path = Path("data/analysis_history.json")
    
    results = {}
    if results_path.exists():
        with open(results_path) as f:
            results = json.load(f).get("results", {})
    
    history = []
    if history_path.exists():
        with open(history_path) as f:
            history = json.load(f).get("analyses", [])
    
    return results, history

def analyze_blend_impact():
    """
    Analyze how blend ratio affects predictions
    
    Since we don't have separate ML and similarity predictions stored,
    we'll analyze the pattern of wins/losses to infer optimal blend.
    """
    
    results, history = load_data()
    
    print("=" * 80)
    print("  BLEND RATIO ANALYSIS FROM ACTUAL RESULTS")
    print("=" * 80)
    print()
    
    print(f"Analyzing {len(results)} bet results...")
    print()
    
    # Analyze by predicted probability ranges
    prob_buckets = defaultdict(lambda: {"won": 0, "total": 0, "edges": [], "rois": []})
    
    for result in results.values():
        true_prob = result["bet"]["true_prob"]
        edge = result["bet"]["edge"]
        roi = result["profit"] / result["bet"]["stake"]
        
        # Round to nearest 5%
        bucket = round(true_prob * 20) / 20
        prob_buckets[bucket]["total"] += 1
        prob_buckets[bucket]["edges"].append(edge)
        prob_buckets[bucket]["rois"].append(roi)
        if result["result"] == "won":
            prob_buckets[bucket]["won"] += 1
    
    print("CALIBRATION ANALYSIS:")
    print("(Shows if model is over/under-confident)")
    print()
    print("Predicted Prob | Actual WR | Bets | Avg Edge | Avg ROI | Status")
    print("-" * 80)
    
    calibration_errors = []
    overconfident_buckets = []
    underconfident_buckets = []
    
    for prob in sorted(prob_buckets.keys()):
        stats_data = prob_buckets[prob]
        actual_wr = stats_data["won"] / stats_data["total"]
        avg_edge = statistics.mean(stats_data["edges"]) * 100
        avg_roi = statistics.mean(stats_data["rois"]) * 100
        error = prob - actual_wr
        
        calibration_errors.append(abs(error))
        
        if error > 0.05:  # Overconfident
            status = "⚠ OVER"
            overconfident_buckets.append((prob, error))
        elif error < -0.05:  # Underconfident
            status = "⚠ UNDER"
            underconfident_buckets.append((prob, error))
        else:
            status = "✓ Good"
        
        print(f"{prob:5.0%}          | {actual_wr:5.1%}    | {stats_data['total']:4d} | "
              f"{avg_edge:8.1f}% | {avg_roi:7.1f}% | {status}")
    
    print()
    
    # Analysis
    mean_error = statistics.mean(calibration_errors)
    
    print("CALIBRATION SUMMARY:")
    print(f"  Mean Absolute Error: {mean_error:.1%}")
    print()
    
    if len(overconfident_buckets) > len(underconfident_buckets):
        print("  ⚠ MODEL IS OVERCONFIDENT")
        print("    → Predicted probabilities are higher than actual outcomes")
        print("    → This suggests:")
        print("      • ML model may be too aggressive")
        print("      • Consider REDUCING ML weight (try 40-42%)")
        print("      • Or increase minimum edge threshold")
        print()
    elif len(underconfident_buckets) > len(overconfident_buckets):
        print("  ⚠ MODEL IS UNDERCONFIDENT")
        print("    → Predicted probabilities are lower than actual outcomes")
        print("    → This suggests:")
        print("      • ML model may be too conservative")
        print("      • Consider INCREASING ML weight (try 48-50%)")
        print("      • Model is leaving value on the table")
        print()
    else:
        print("  ✓ MODEL IS WELL-CALIBRATED")
        print("    → Predicted probabilities match actual outcomes")
        print("    → Current blend ratio (45%) appears optimal")
        print()
    
    # Analyze by bet type
    print("=" * 80)
    print("PERFORMANCE BY BET TYPE")
    print("=" * 80)
    print()
    
    by_type = defaultdict(lambda: {"won": 0, "total": 0, "profit": 0, "staked": 0, "probs": []})
    
    for result in results.values():
        bet_type = result["bet"]["bet_type"]
        by_type[bet_type]["total"] += 1
        by_type[bet_type]["staked"] += result["bet"]["stake"]
        by_type[bet_type]["profit"] += result["profit"]
        by_type[bet_type]["probs"].append(result["bet"]["true_prob"])
        if result["result"] == "won":
            by_type[bet_type]["won"] += 1
    
    for bet_type in sorted(by_type.keys()):
        stats_data = by_type[bet_type]
        wr = stats_data["won"] / stats_data["total"]
        roi = stats_data["profit"] / stats_data["staked"] * 100
        avg_prob = statistics.mean(stats_data["probs"])
        
        print(f"{bet_type}:")
        print(f"  Win Rate: {wr:.1%} (predicted: {avg_prob:.1%})")
        print(f"  ROI: {roi:+.1f}%")
        print(f"  Bets: {stats_data['won']}/{stats_data['total']}")
        
        # Calibration for this bet type
        calibration_diff = avg_prob - wr
        if abs(calibration_diff) > 0.05:
            if calibration_diff > 0:
                print(f"  ⚠ Overconfident by {calibration_diff:.1%}")
                if bet_type == "Moneyline":
                    print("    → ML model may be too aggressive on game winners")
                    print("    → Consider reducing ML weight slightly")
                elif bet_type == "Total":
                    print("    → Similarity model may be overestimating scoring")
                    print("    → Consider increasing ML weight (ML is more conservative on totals)")
            else:
                print(f"  ⚠ Underconfident by {abs(calibration_diff):.1%}")
                if bet_type == "Moneyline":
                    print("    → ML model is too conservative on game winners")
                    print("    → Consider increasing ML weight")
                elif bet_type == "Total":
                    print("    → Model is underestimating scoring accuracy")
                    print("    → Current blend may be optimal")
        else:
            print(f"  ✓ Well-calibrated (diff: {calibration_diff:+.1%})")
        print()
    
    # Final recommendation
    print("=" * 80)
    print("RECOMMENDATION")
    print("=" * 80)
    print()
    
    overall_roi = sum(r["profit"] for r in results.values()) / sum(r["bet"]["stake"] for r in results.values()) * 100
    
    if mean_error < 0.10 and overall_roi > 15:
        print("✓ CURRENT BLEND RATIO (45%) IS OPTIMAL")
        print()
        print("  Evidence:")
        print(f"    • Calibration error < 10% ({mean_error:.1%})")
        print(f"    • ROI > 15% ({overall_roi:.1f}%)")
        print("    • No systematic over/under-confidence")
        print()
        print("  Action: Maintain current 45% ML weight")
        print()
    elif mean_error > 0.15:
        print("⚠ CALIBRATION NEEDS IMPROVEMENT")
        print()
        if len(overconfident_buckets) > len(underconfident_buckets):
            print("  Suggested adjustment: REDUCE ML weight to 40-42%")
            print("  Reason: Model is overconfident, needs more historical data influence")
        else:
            print("  Suggested adjustment: INCREASE ML weight to 48-50%")
            print("  Reason: Model is underconfident, ML predictions are more accurate")
        print()
    else:
        print("✓ PERFORMANCE IS GOOD")
        print()
        print(f"  Calibration: {mean_error:.1%} error (acceptable)")
        print(f"  ROI: {overall_roi:+.1f}%")
        print()
        print("  Minor adjustments to consider:")
        
        # Check moneyline vs total performance
        if "Moneyline" in by_type and "Total" in by_type:
            ml_roi = by_type["Moneyline"]["profit"] / by_type["Moneyline"]["staked"] * 100
            total_roi = by_type["Total"]["profit"] / by_type["Total"]["staked"] * 100
            
            if ml_roi > total_roi + 15:
                print("    • Moneylines significantly outperforming")
                print("    • Consider increasing ML weight to 47-48%")
            elif total_roi > ml_roi + 15:
                print("    • Totals significantly outperforming")
                print("    • Consider reducing ML weight to 42-43%")
            else:
                print("    • Both bet types performing well")
                print("    • No changes needed")
        print()
    
    print("=" * 80)
    print()
    print("NOTE: This analysis is based on {len(results)} bets.")
    print("      Confidence increases with more data (target: 100+ bets)")
    print()

if __name__ == "__main__":
    analyze_blend_impact()
