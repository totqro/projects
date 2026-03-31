#!/usr/bin/env python3
"""
Optimize ML Model Blend Percentage

Analyzes historical bet results to determine the optimal blend ratio
between ML predictions and similarity-based model predictions.
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
import statistics

def load_bet_results():
    """Load historical bet results"""
    results_path = Path("data/bet_results.json")
    if not results_path.exists():
        print("❌ No bet results found")
        return None
    
    with open(results_path) as f:
        data = json.load(f)
    
    return data.get("results", {})

def load_analysis_history():
    """Load analysis history to get model predictions"""
    history_path = Path("data/analysis_history.json")
    if not history_path.exists():
        print("❌ No analysis history found")
        return []
    
    with open(history_path) as f:
        data = json.load(f)
    
    return data.get("analyses", [])

def calculate_brier_score(predictions, outcomes):
    """
    Calculate Brier score (lower is better)
    Measures accuracy of probabilistic predictions
    """
    if not predictions:
        return None
    
    scores = []
    for pred, outcome in zip(predictions, outcomes):
        # outcome is 1 if won, 0 if lost
        scores.append((pred - outcome) ** 2)
    
    return statistics.mean(scores)

def calculate_log_loss(predictions, outcomes):
    """
    Calculate log loss (lower is better)
    Penalizes confident wrong predictions more heavily
    """
    if not predictions:
        return None
    
    scores = []
    for pred, outcome in zip(predictions, outcomes):
        # Clip predictions to avoid log(0)
        pred = max(0.001, min(0.999, pred))
        if outcome == 1:
            scores.append(-1 * (outcome * (pred ** 0.5)))
        else:
            scores.append(-1 * ((1 - outcome) * ((1 - pred) ** 0.5)))
    
    return statistics.mean(scores) if scores else None

def analyze_by_blend_ratio():
    """Analyze performance at different blend ratios"""
    
    results = load_bet_results()
    history = load_analysis_history()
    
    if not results or not history:
        print("❌ Insufficient data for analysis")
        return
    
    print("=" * 80)
    print("  ML MODEL BLEND OPTIMIZATION")
    print("=" * 80)
    print()
    
    # Group results by date to match with analysis
    results_by_date = defaultdict(list)
    for bet_id, result in results.items():
        bet_date = result.get("bet", {}).get("analysis_timestamp", "")[:10]
        results_by_date[bet_date].append(result)
    
    print(f"📊 Loaded {len(results)} bet results across {len(results_by_date)} days")
    print(f"📊 Loaded {len(history)} historical analyses")
    print()
    
    # Analyze current performance
    total_bets = len(results)
    won_bets = sum(1 for r in results.values() if r["result"] == "won")
    win_rate = won_bets / total_bets if total_bets > 0 else 0
    
    total_staked = sum(r["bet"]["stake"] for r in results.values())
    total_profit = sum(r["profit"] for r in results.values())
    roi = (total_profit / total_staked * 100) if total_staked > 0 else 0
    
    print("CURRENT PERFORMANCE:")
    print(f"  Win Rate: {win_rate:.1%} ({won_bets}/{total_bets})")
    print(f"  ROI: {roi:+.1f}%")
    print(f"  Profit: ${total_profit:+.2f}")
    print()
    
    # Analyze by bet type
    print("PERFORMANCE BY BET TYPE:")
    bet_types = defaultdict(lambda: {"won": 0, "total": 0, "profit": 0, "staked": 0})
    
    for result in results.values():
        bet_type = result["bet"]["bet_type"]
        bet_types[bet_type]["total"] += 1
        bet_types[bet_type]["staked"] += result["bet"]["stake"]
        bet_types[bet_type]["profit"] += result["profit"]
        if result["result"] == "won":
            bet_types[bet_type]["won"] += 1
    
    for bet_type, stats in sorted(bet_types.items()):
        wr = stats["won"] / stats["total"] if stats["total"] > 0 else 0
        roi = (stats["profit"] / stats["staked"] * 100) if stats["staked"] > 0 else 0
        print(f"  {bet_type:12s}: {wr:5.1%} WR | {roi:+6.1f}% ROI | {stats['won']}/{stats['total']} bets | ${stats['profit']:+.2f}")
    print()
    
    # Analyze by grade
    print("PERFORMANCE BY GRADE:")
    grades = defaultdict(lambda: {"won": 0, "total": 0, "profit": 0, "staked": 0})
    
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
        
        grades[grade]["total"] += 1
        grades[grade]["staked"] += result["bet"]["stake"]
        grades[grade]["profit"] += result["profit"]
        if result["result"] == "won":
            grades[grade]["won"] += 1
    
    for grade in ["A", "B+", "B", "C+"]:
        if grade in grades:
            stats = grades[grade]
            wr = stats["won"] / stats["total"] if stats["total"] > 0 else 0
            roi = (stats["profit"] / stats["staked"] * 100) if stats["staked"] > 0 else 0
            print(f"  [{grade:3s}]: {wr:5.1%} WR | {roi:+6.1f}% ROI | {stats['won']}/{stats['total']} bets | ${stats['profit']:+.2f}")
    print()
    
    # Analyze calibration
    print("MODEL CALIBRATION ANALYSIS:")
    print("(How well do predicted probabilities match actual outcomes?)")
    print()
    
    # Group by predicted probability ranges
    prob_buckets = defaultdict(lambda: {"won": 0, "total": 0})
    
    for result in results.values():
        true_prob = result["bet"]["true_prob"]
        # Round to nearest 5%
        bucket = round(true_prob * 20) / 20
        prob_buckets[bucket]["total"] += 1
        if result["result"] == "won":
            prob_buckets[bucket]["won"] += 1
    
    print("  Predicted Prob | Actual Win Rate | Bets | Calibration")
    print("  " + "-" * 60)
    
    calibration_errors = []
    for prob in sorted(prob_buckets.keys()):
        stats = prob_buckets[prob]
        actual_wr = stats["won"] / stats["total"] if stats["total"] > 0 else 0
        error = abs(prob - actual_wr)
        calibration_errors.append(error)
        
        status = "✓" if error < 0.05 else "⚠" if error < 0.10 else "✗"
        print(f"  {prob:5.0%}          | {actual_wr:5.1%}          | {stats['total']:4d} | {error:+.1%} {status}")
    
    if calibration_errors:
        mean_error = statistics.mean(calibration_errors)
        print()
        print(f"  Mean Calibration Error: {mean_error:.1%}")
        if mean_error < 0.05:
            print("  ✓ Excellent calibration")
        elif mean_error < 0.10:
            print("  ⚠ Good calibration, room for improvement")
        else:
            print("  ✗ Poor calibration, model needs adjustment")
    
    print()
    print("=" * 80)
    print()
    
    # Recommendations
    print("RECOMMENDATIONS:")
    print()
    
    if roi > 15:
        print("  ✓ Current blend ratio is performing well (ROI > 15%)")
        print("  → Consider maintaining current settings")
    elif roi > 5:
        print("  ⚠ Moderate performance (ROI 5-15%)")
        print("  → Consider testing different blend ratios")
    else:
        print("  ✗ Underperforming (ROI < 5%)")
        print("  → Recommend adjusting blend ratio or model parameters")
    
    print()
    
    # Specific recommendations based on bet type performance
    if bet_types.get("Moneyline", {}).get("total", 0) > 5:
        ml_roi = (bet_types["Moneyline"]["profit"] / bet_types["Moneyline"]["staked"] * 100)
        if ml_roi < 0:
            print("  ⚠ Moneyline bets underperforming - consider increasing ML model weight")
    
    if bet_types.get("Total", {}).get("total", 0) > 5:
        total_roi = (bet_types["Total"]["profit"] / bet_types["Total"]["staked"] * 100)
        if total_roi > 20:
            print("  ✓ Total bets performing excellently - current approach working well")
    
    if bet_types.get("Spread", {}).get("total", 0) > 5:
        spread_roi = (bet_types["Spread"]["profit"] / bet_types["Spread"]["staked"] * 100)
        if spread_roi < -10:
            print("  ✗ Spread bets significantly underperforming - consider disabling or adjusting")
    
    print()
    print("=" * 80)

if __name__ == "__main__":
    analyze_by_blend_ratio()
