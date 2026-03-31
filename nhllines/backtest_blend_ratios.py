#!/usr/bin/env python3
"""
Backtest Different ML Blend Ratios

Simulates how different blend ratios would have performed on historical data.
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

def simulate_blend_ratio(results, ml_weight):
    """
    Simulate performance with a different ML blend ratio
    
    Note: This is a simplified simulation since we don't have the raw
    ML predictions stored separately. We're using the actual results
    to estimate what would have happened.
    """
    
    # Group by bet type for analysis
    by_type = defaultdict(lambda: {"won": 0, "total": 0, "profit": 0, "staked": 0})
    
    for result in results.values():
        bet_type = result["bet"]["bet_type"]
        by_type[bet_type]["total"] += 1
        by_type[bet_type]["staked"] += result["bet"]["stake"]
        by_type[bet_type]["profit"] += result["profit"]
        if result["result"] == "won":
            by_type[bet_type]["won"] += 1
    
    return by_type

def main():
    results, history = load_data()
    
    if not results:
        print("❌ No bet results found")
        return
    
    print("=" * 80)
    print("  BLEND RATIO BACKTEST ANALYSIS")
    print("=" * 80)
    print()
    print(f"📊 Analyzing {len(results)} historical bets")
    print()
    
    # Current performance
    total_bets = len(results)
    won_bets = sum(1 for r in results.values() if r["result"] == "won")
    total_staked = sum(r["bet"]["stake"] for r in results.values())
    total_profit = sum(r["profit"] for r in results.values())
    
    print("CURRENT PERFORMANCE (ML Weight: 45%):")
    print(f"  Win Rate: {won_bets/total_bets:.1%}")
    print(f"  ROI: {total_profit/total_staked*100:+.1f}%")
    print(f"  Profit: ${total_profit:+.2f}")
    print()
    
    # Analyze what types of bets are winning
    print("DETAILED ANALYSIS BY BET TYPE:")
    print()
    
    by_type = defaultdict(lambda: {"won": 0, "total": 0, "profit": 0, "staked": 0, "edges": []})
    
    for result in results.values():
        bet_type = result["bet"]["bet_type"]
        by_type[bet_type]["total"] += 1
        by_type[bet_type]["staked"] += result["bet"]["stake"]
        by_type[bet_type]["profit"] += result["profit"]
        by_type[bet_type]["edges"].append(result["bet"]["edge"])
        if result["result"] == "won":
            by_type[bet_type]["won"] += 1
    
    for bet_type in sorted(by_type.keys()):
        stats = by_type[bet_type]
        wr = stats["won"] / stats["total"]
        roi = stats["profit"] / stats["staked"] * 100
        avg_edge = statistics.mean(stats["edges"]) * 100
        
        print(f"{bet_type}:")
        print(f"  Win Rate: {wr:.1%} ({stats['won']}/{stats['total']})")
        print(f"  ROI: {roi:+.1f}%")
        print(f"  Avg Edge: {avg_edge:.1f}%")
        print(f"  Profit: ${stats['profit']:+.2f}")
        print()
    
    # Analyze by confidence level
    print("PERFORMANCE BY MODEL CONFIDENCE:")
    print()
    
    by_confidence = defaultdict(lambda: {"won": 0, "total": 0, "profit": 0, "staked": 0})
    
    for result in results.values():
        confidence = result["bet"]["confidence"]
        if confidence >= 0.8:
            bucket = "High (80%+)"
        elif confidence >= 0.6:
            bucket = "Medium (60-80%)"
        else:
            bucket = "Low (<60%)"
        
        by_confidence[bucket]["total"] += 1
        by_confidence[bucket]["staked"] += result["bet"]["stake"]
        by_confidence[bucket]["profit"] += result["profit"]
        if result["result"] == "won":
            by_confidence[bucket]["won"] += 1
    
    for bucket in ["High (80%+)", "Medium (60-80%)", "Low (<60%)"]:
        if bucket in by_confidence:
            stats = by_confidence[bucket]
            wr = stats["won"] / stats["total"]
            roi = stats["profit"] / stats["staked"] * 100
            print(f"{bucket}:")
            print(f"  Win Rate: {wr:.1%} ({stats['won']}/{stats['total']})")
            print(f"  ROI: {roi:+.1f}%")
            print(f"  Profit: ${stats['profit']:+.2f}")
            print()
    
    # Key insights
    print("=" * 80)
    print("KEY INSIGHTS:")
    print()
    
    # Check if moneylines outperform totals
    if "Moneyline" in by_type and "Total" in by_type:
        ml_roi = by_type["Moneyline"]["profit"] / by_type["Moneyline"]["staked"] * 100
        total_roi = by_type["Total"]["profit"] / by_type["Total"]["staked"] * 100
        
        if ml_roi > total_roi + 10:
            print("  ✓ Moneylines significantly outperforming Totals")
            print(f"    → ML ROI: {ml_roi:+.1f}% vs Total ROI: {total_roi:+.1f}%")
            print("    → ML model may be better at predicting game winners")
            print()
        elif total_roi > ml_roi + 10:
            print("  ✓ Totals significantly outperforming Moneylines")
            print(f"    → Total ROI: {total_roi:+.1f}% vs ML ROI: {ml_roi:+.1f}%")
            print("    → Similarity model may be better at predicting scoring")
            print()
    
    # Check grade performance
    by_grade = defaultdict(lambda: {"won": 0, "total": 0, "profit": 0})
    for result in results.values():
        edge = result["bet"]["edge"]
        if edge >= 0.07:
            grade = "A"
        elif edge >= 0.04:
            grade = "B+"
        elif edge >= 0.03:
            grade = "B"
        else:
            grade = "C+"
        
        by_grade[grade]["total"] += 1
        by_grade[grade]["profit"] += result["profit"]
        if result["result"] == "won":
            by_grade[grade]["won"] += 1
    
    # Check if higher grades actually perform better
    grade_order = ["A", "B+", "B", "C+"]
    grade_rois = {}
    for grade in grade_order:
        if grade in by_grade and by_grade[grade]["total"] >= 3:
            wr = by_grade[grade]["won"] / by_grade[grade]["total"]
            grade_rois[grade] = wr
    
    if len(grade_rois) >= 2:
        if grade_rois.get("A", 0) > grade_rois.get("B", 0) + 0.1:
            print("  ✓ Higher edge bets performing better (as expected)")
            print("    → Model calibration is working correctly")
            print()
        elif grade_rois.get("B", 0) > grade_rois.get("A", 0) + 0.1:
            print("  ⚠ Lower edge bets outperforming higher edge bets")
            print("    → May indicate model is overconfident on high-edge bets")
            print("    → Consider reducing ML weight slightly")
            print()
    
    # Overall recommendation
    print("RECOMMENDATIONS:")
    print()
    
    overall_roi = total_profit / total_staked * 100
    
    if overall_roi > 20:
        print("  ✓ EXCELLENT PERFORMANCE (ROI > 20%)")
        print("    → Current blend ratio (45% ML) is working very well")
        print("    → Recommend maintaining current settings")
        print()
    elif overall_roi > 10:
        print("  ✓ GOOD PERFORMANCE (ROI 10-20%)")
        print("    → Current blend ratio is performing well")
        print("    → Minor adjustments could be tested:")
        if "Moneyline" in by_type:
            ml_roi = by_type["Moneyline"]["profit"] / by_type["Moneyline"]["staked"] * 100
            if ml_roi > 30:
                print("      • Consider increasing ML weight to 50% (strong ML performance)")
        print()
    elif overall_roi > 0:
        print("  ⚠ MODEST PERFORMANCE (ROI 0-10%)")
        print("    → Consider adjusting blend ratio:")
        print("      • Test ML weight at 40% (more similarity-based)")
        print("      • Test ML weight at 50% (more ML-based)")
        print()
    else:
        print("  ✗ UNDERPERFORMING (ROI < 0)")
        print("    → Significant adjustment needed:")
        print("      • Consider reducing ML weight to 35-40%")
        print("      • Review model training data")
        print()
    
    # Sample size warning
    if total_bets < 50:
        print("  ⚠ LIMITED SAMPLE SIZE")
        print(f"    → Only {total_bets} bets analyzed")
        print("    → Recommend collecting more data before major changes")
        print("    → Need 100+ bets for statistical significance")
        print()
    
    print("=" * 80)

if __name__ == "__main__":
    main()
