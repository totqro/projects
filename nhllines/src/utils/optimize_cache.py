#!/usr/bin/env python3
"""
Cache Optimization Utility
Cleans up old cache files and provides cache statistics.
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
import os


CACHE_DIR = Path(__file__).parent / "cache"


def get_cache_stats():
    """Get statistics about the cache directory."""
    if not CACHE_DIR.exists():
        return None
    
    files = list(CACHE_DIR.glob("*.json"))
    total_size = sum(f.stat().st_size for f in files)
    
    # Group by type
    by_type = {
        "odds": [],
        "schedule": [],
        "scores": [],
        "standings": [],
        "season_games": [],
        "player_data": [],
        "other": []
    }
    
    for f in files:
        name = f.name
        if "odds_" in name:
            by_type["odds"].append(f)
        elif "schedule_" in name:
            by_type["schedule"].append(f)
        elif "scores_" in name:
            by_type["scores"].append(f)
        elif "standings_" in name:
            by_type["standings"].append(f)
        elif "season_games_" in name:
            by_type["season_games"].append(f)
        elif "player_data_" in name:
            by_type["player_data"].append(f)
        else:
            by_type["other"].append(f)
    
    return {
        "total_files": len(files),
        "total_size_mb": total_size / (1024 * 1024),
        "by_type": {k: len(v) for k, v in by_type.items()},
        "by_type_files": by_type,
    }


def clean_old_cache(days_old: int = 7):
    """Remove cache files older than specified days."""
    if not CACHE_DIR.exists():
        print("No cache directory found.")
        return
    
    cutoff = datetime.now() - timedelta(days=days_old)
    removed = 0
    freed_bytes = 0
    
    for f in CACHE_DIR.glob("*.json"):
        # Skip quota_info (always keep)
        if f.name == "quota_info.json":
            continue
        
        # Skip season_games cache (expensive to rebuild)
        if "season_games_" in f.name:
            continue
        
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        if mtime < cutoff:
            size = f.stat().st_size
            f.unlink()
            removed += 1
            freed_bytes += size
    
    print(f"✅ Removed {removed} old cache files")
    print(f"   Freed {freed_bytes / (1024 * 1024):.2f} MB")


def print_cache_summary():
    """Print a summary of cache usage."""
    stats = get_cache_stats()
    
    if not stats:
        print("No cache found.")
        return
    
    print("\n" + "=" * 60)
    print("  CACHE STATISTICS")
    print("=" * 60)
    print(f"  Total files: {stats['total_files']}")
    print(f"  Total size: {stats['total_size_mb']:.2f} MB")
    print()
    print("  By type:")
    for type_name, count in stats['by_type'].items():
        if count > 0:
            files = stats['by_type_files'][type_name]
            size = sum(f.stat().st_size for f in files) / (1024 * 1024)
            print(f"    {type_name:15s}: {count:3d} files ({size:.2f} MB)")
    print("=" * 60)


def optimize_cache():
    """Run full cache optimization."""
    print("Running cache optimization...")
    print()
    
    # Show current stats
    print_cache_summary()
    
    # Clean old files
    print()
    clean_old_cache(days_old=7)
    
    # Show new stats
    print()
    print_cache_summary()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Cache Optimization Utility")
    parser.add_argument("--stats", action="store_true",
                       help="Show cache statistics")
    parser.add_argument("--clean", action="store_true",
                       help="Clean old cache files")
    parser.add_argument("--days", type=int, default=7,
                       help="Days old to clean (default: 7)")
    parser.add_argument("--optimize", action="store_true",
                       help="Run full optimization")
    args = parser.parse_args()
    
    if args.stats:
        print_cache_summary()
    elif args.clean:
        clean_old_cache(days_old=args.days)
    elif args.optimize:
        optimize_cache()
    else:
        print("Use --stats, --clean, or --optimize")
        print("Example: python optimize_cache.py --optimize")
