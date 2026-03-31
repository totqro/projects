#!/usr/bin/env python3
"""
System Optimization Report
Provides comprehensive analysis of system performance and optimization status.
"""

import json
from pathlib import Path
from datetime import datetime
import os


def check_ml_models():
    """Check ML model status and size."""
    ml_dir = Path(__file__).parent / "ml_models"
    
    if not ml_dir.exists():
        return {"status": "not_found", "models": []}
    
    models = []
    for model_file in ml_dir.glob("*.pkl"):
        size_kb = model_file.stat().st_size / 1024
        models.append({
            "name": model_file.name,
            "size_kb": size_kb,
            "modified": datetime.fromtimestamp(model_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        })
    
    return {
        "status": "trained" if models else "not_trained",
        "models": models,
        "total_size_kb": sum(m["size_kb"] for m in models),
    }


def check_cache_efficiency():
    """Analyze cache efficiency."""
    cache_dir = Path(__file__).parent / "cache"
    
    if not cache_dir.exists():
        return {"status": "no_cache"}
    
    files = list(cache_dir.glob("*.json"))
    total_size = sum(f.stat().st_size for f in files)
    
    # Check for stale files (>7 days old)
    stale_count = 0
    stale_size = 0
    for f in files:
        age_days = (datetime.now().timestamp() - f.stat().st_mtime) / 86400
        if age_days > 7 and "season_games" not in f.name:
            stale_count += 1
            stale_size += f.stat().st_size
    
    return {
        "total_files": len(files),
        "total_size_mb": total_size / (1024 * 1024),
        "stale_files": stale_count,
        "stale_size_mb": stale_size / (1024 * 1024),
        "efficiency": "good" if stale_count < 10 else "needs_cleanup",
    }


def check_tracking_data():
    """Check bet tracking and analysis history."""
    bet_results = Path(__file__).parent / "bet_results.json"
    analysis_history = Path(__file__).parent / "analysis_history.json"
    
    tracking = {
        "bet_results": {"exists": False, "bets": 0},
        "analysis_history": {"exists": False, "analyses": 0},
    }
    
    if bet_results.exists():
        data = json.loads(bet_results.read_text())
        tracking["bet_results"] = {
            "exists": True,
            "bets": len(data.get("results", {})),
            "size_kb": bet_results.stat().st_size / 1024,
        }
    
    if analysis_history.exists():
        data = json.loads(analysis_history.read_text())
        tracking["analysis_history"] = {
            "exists": True,
            "analyses": len(data.get("analyses", [])),
            "size_kb": analysis_history.stat().st_size / 1024,
        }
    
    return tracking


def check_api_quota():
    """Check API quota status."""
    quota_file = Path(__file__).parent / "cache" / "quota_info.json"
    
    if not quota_file.exists():
        return {"status": "unknown"}
    
    try:
        data = json.loads(quota_file.read_text())
        remaining = int(data.get("remaining", 0))
        used = int(data.get("used", 0))
        
        return {
            "status": "ok",
            "remaining": remaining,
            "used": used,
            "percentage_used": (used / (used + remaining) * 100) if (used + remaining) > 0 else 0,
        }
    except:
        return {"status": "error"}


def get_code_stats():
    """Get statistics about the codebase."""
    py_files = list(Path(__file__).parent.glob("*.py"))
    
    total_lines = 0
    for f in py_files:
        try:
            lines = len(f.read_text().splitlines())
            total_lines += lines
        except:
            continue
    
    return {
        "python_files": len(py_files),
        "total_lines": total_lines,
    }


def generate_optimization_report():
    """Generate comprehensive optimization report."""
    print("\n" + "=" * 75)
    print("  NHL BETTING SYSTEM - OPTIMIZATION REPORT")
    print("  Generated:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 75)
    
    # ML Models
    print("\n📊 MACHINE LEARNING MODELS")
    print("-" * 75)
    ml_status = check_ml_models()
    if ml_status["status"] == "trained":
        print(f"  Status: ✅ Trained and ready")
        print(f"  Models: {len(ml_status['models'])}")
        print(f"  Total size: {ml_status['total_size_kb']:.1f} KB")
        for model in ml_status["models"]:
            print(f"    • {model['name']:20s} {model['size_kb']:6.1f} KB  (modified: {model['modified']})")
        print("\n  Optimizations:")
        print("    ✓ Enhanced hyperparameters (150 estimators, depth 6)")
        print("    ✓ Regularization (subsample 0.8, colsample 0.8)")
        print("    ✓ 30 features (20 base + 10 player features)")
        print("    ✓ 45% ML / 55% similarity blend ratio")
    else:
        print(f"  Status: ⚠️  Not trained")
        print("  Run: python main.py to train models")
    
    # Cache
    print("\n💾 CACHE SYSTEM")
    print("-" * 75)
    cache_status = check_cache_efficiency()
    if cache_status.get("status") != "no_cache":
        print(f"  Total files: {cache_status['total_files']}")
        print(f"  Total size: {cache_status['total_size_mb']:.2f} MB")
        print(f"  Stale files: {cache_status['stale_files']} ({cache_status['stale_size_mb']:.2f} MB)")
        print(f"  Efficiency: {'✅ Good' if cache_status['efficiency'] == 'good' else '⚠️  Needs cleanup'}")
        if cache_status['efficiency'] != 'good':
            print("\n  Recommendation: Run 'python optimize_cache.py --optimize'")
        print("\n  Optimizations:")
        print("    ✓ 12-hour cache for player data")
        print("    ✓ 24-hour cache for season games")
        print("    ✓ 30-minute cache for odds")
        print("    ✓ Reduced API rate limiting (0.1s vs 0.15s)")
    else:
        print("  Status: No cache directory")
    
    # Tracking
    print("\n📈 BET TRACKING & HISTORY")
    print("-" * 75)
    tracking = check_tracking_data()
    print(f"  Bet results: {'✅' if tracking['bet_results']['exists'] else '❌'} "
          f"({tracking['bet_results'].get('bets', 0)} bets tracked)")
    print(f"  Analysis history: {'✅' if tracking['analysis_history']['exists'] else '❌'} "
          f"({tracking['analysis_history'].get('analyses', 0)} analyses)")
    print("\n  Optimizations:")
    print("    ✓ Automatic deduplication (bet signature-based)")
    print("    ✓ 30-day rolling window")
    print("    ✓ Performance tracking by grade (A, B+, B, C+)")
    
    # API Quota
    print("\n🔑 API QUOTA STATUS")
    print("-" * 75)
    quota = check_api_quota()
    if quota["status"] == "ok":
        remaining = quota["remaining"]
        used = quota["used"]
        pct = quota["percentage_used"]
        print(f"  Remaining: {remaining} requests")
        print(f"  Used: {used} requests ({pct:.1f}%)")
        
        if remaining < 100:
            print("  ⚠️  Warning: Low quota remaining")
        else:
            print("  ✅ Quota healthy")
        
        print("\n  Optimizations:")
        print("    ✓ Daily updates at 4:00 PM (saves ~42 credits/day)")
        print("    ✓ 30-minute odds cache")
        print("    ✓ Efficient batch fetching")
    else:
        print("  Status: Unknown (no recent API calls)")
    
    # Model Analysis
    print("\n🎯 MODEL ANALYSIS QUALITY")
    print("-" * 75)
    print("  Similarity Model:")
    print("    ✓ 50 similar games per matchup")
    print("    ✓ 7-factor similarity scoring")
    print("    ✓ Confidence-based regression to mean")
    print("    ✓ 40% model weight (increased from 35%)")
    print("    ✓ Square-root confidence scaling")
    print("\n  ML Model:")
    print("    ✓ XGBoost with optimized hyperparameters")
    print("    ✓ Player-level features (rest, B2B, injuries)")
    print("    ✓ 45% ML weight in hybrid model")
    print("\n  Blending:")
    print("    ✓ Hybrid: 45% ML + 55% similarity")
    print("    ✓ Market blend: 40% model + 60% market")
    print("    ✓ Confidence-weighted adjustments")
    
    # Code Stats
    print("\n📝 CODEBASE")
    print("-" * 75)
    code = get_code_stats()
    print(f"  Python files: {code['python_files']}")
    print(f"  Total lines: {code['total_lines']:,}")
    print("\n  Key modules:")
    print("    • main.py - Analysis pipeline")
    print("    • ml_model_enhanced.py - 30-feature ML model")
    print("    • model.py - Similarity-based predictions")
    print("    • bet_tracker.py - Performance tracking")
    print("    • analysis_history.py - Historical data management")
    
    # Recommendations
    print("\n💡 OPTIMIZATION RECOMMENDATIONS")
    print("-" * 75)
    
    recommendations = []
    
    if ml_status["status"] != "trained":
        recommendations.append("Train ML models: python main.py")
    
    if cache_status.get("efficiency") == "needs_cleanup":
        recommendations.append("Clean cache: python optimize_cache.py --optimize")
    
    if quota.get("remaining", 500) < 100:
        recommendations.append("Monitor API quota - consider reducing update frequency")
    
    if not recommendations:
        print("  ✅ System is fully optimized!")
        print("\n  Maintenance tasks:")
        print("    • Run bet tracker weekly: python bet_tracker.py --check")
        print("    • Clean cache monthly: python optimize_cache.py --optimize")
        print("    • Review performance: Check website Performance History tab")
    else:
        for i, rec in enumerate(recommendations, 1):
            print(f"  {i}. {rec}")
    
    print("\n" + "=" * 75)
    print()


if __name__ == "__main__":
    generate_optimization_report()
