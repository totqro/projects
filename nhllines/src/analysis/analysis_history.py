"""
Analysis History Manager
Saves all analysis outputs, removes duplicates, and maintains 30-day rolling history.
"""

import json
from pathlib import Path
from datetime import datetime, timedelta, timezone


HISTORY_PATH = Path(__file__).parent.parent.parent / "data" / "analysis_history.json"
MAX_DAYS = 30

# EST = UTC-4
EST = timezone(timedelta(hours=-4))


def _parse_timestamp(ts_str: str) -> datetime:
    """Parse a timestamp string, normalizing everything to EST."""
    dt = datetime.fromisoformat(ts_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=EST)
    else:
        dt = dt.astimezone(EST)
    return dt


def save_analysis(analysis_data: dict):
    """
    Save analysis to history, removing duplicates and old entries.
    Deduplicates based on the actual bet recommendations, not just timestamp.
    
    Args:
        analysis_data: The analysis output from main.py
    """
    # Load existing history
    if HISTORY_PATH.exists():
        history = json.loads(HISTORY_PATH.read_text())
    else:
        history = {"analyses": []}
    
    # Add timestamp if not present (EST)
    if "timestamp" not in analysis_data:
        analysis_data["timestamp"] = datetime.now(EST).isoformat()

    new_timestamp = _parse_timestamp(analysis_data["timestamp"])
    
    # Create a signature for this analysis based on recommendations
    def get_analysis_signature(analysis):
        """Create a unique signature based on the bets recommended."""
        recs = analysis.get("recommendations", [])
        if not recs:
            return None
        # Sort by game and pick to create consistent signature
        sig_parts = []
        for rec in sorted(recs, key=lambda r: (r.get("game", ""), r.get("pick", ""))):
            sig_parts.append(f"{rec.get('game', '')}_{rec.get('pick', '')}")
        return "|".join(sig_parts)
    
    new_sig = get_analysis_signature(analysis_data)
    
    # Remove duplicates and old entries
    cutoff_date = datetime.now(EST) - timedelta(days=MAX_DAYS)
    filtered = []

    for existing in history["analyses"]:
        existing_time = _parse_timestamp(existing["timestamp"])
        
        # Skip if too old
        if existing_time < cutoff_date:
            continue
        
        # Skip if duplicate signature (same bets)
        if new_sig and get_analysis_signature(existing) == new_sig:
            continue
        
        # Skip if very close in time (within 5 minutes)
        time_diff = abs((existing_time - new_timestamp).total_seconds())
        if time_diff < 300:  # 5 minutes
            continue
        
        filtered.append(existing)
    
    # Add new analysis
    filtered.append(analysis_data)
    
    # Sort by timestamp (newest first)
    filtered.sort(key=lambda x: x["timestamp"], reverse=True)
    
    # Save
    history["analyses"] = filtered
    history["last_updated"] = datetime.now(EST).isoformat()
    history["total_analyses"] = len(filtered)
    
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(history, indent=2, default=str))
    
    # Clean up old entries
    removed = len(history["analyses"]) - len(filtered)
    if removed > 0:
        print(f"  📁 Cleaned up {removed} old/duplicate entries")
    
    print(f"  📁 Saved to history ({len(filtered)} analyses in last {MAX_DAYS} days)")


def get_all_bets_from_history(days_back: int = 30):
    """
    Get all bets from historical analyses.
    
    Args:
        days_back: How many days back to retrieve
    
    Returns:
        list: All bets from the specified time period
    """
    if not HISTORY_PATH.exists():
        return []
    
    history = json.loads(HISTORY_PATH.read_text())
    cutoff = datetime.now(EST) - timedelta(days=days_back)

    all_bets = []
    for analysis in history["analyses"]:
        analysis_time = _parse_timestamp(analysis["timestamp"])
        if analysis_time < cutoff:
            continue
        
        # Extract bets from recommendations
        if "recommendations" in analysis:
            for bet in analysis["recommendations"]:
                # Skip .0 total lines — they can push and shouldn't be tracked
                if bet.get("bet_type") == "Total":
                    line = float(bet["pick"].split()[1])
                    if line == int(line):
                        continue
                # Add analysis timestamp to bet
                bet_with_time = {**bet, "analysis_timestamp": analysis["timestamp"]}
                all_bets.append(bet_with_time)
    
    return all_bets


def get_history_stats(days_back: int = 30):
    """
    Get statistics about the analysis history.
    
    Returns:
        dict: Statistics about saved analyses
    """
    if not HISTORY_PATH.exists():
        return None
    
    history = json.loads(HISTORY_PATH.read_text())
    cutoff = datetime.now(EST) - timedelta(days=days_back)

    recent = [a for a in history["analyses"]
              if _parse_timestamp(a["timestamp"]) >= cutoff]
    
    if not recent:
        return None
    
    total_bets = sum(len(a.get("recommendations", [])) for a in recent)
    total_games = sum(len(a.get("games_analyzed", [])) for a in recent)
    
    # Get date range
    timestamps = [_parse_timestamp(a["timestamp"]) for a in recent]
    oldest = min(timestamps)
    newest = max(timestamps)
    
    return {
        "total_analyses": len(recent),
        "total_bets_recommended": total_bets,
        "total_games_analyzed": total_games,
        "oldest_analysis": oldest.strftime("%Y-%m-%d %H:%M"),
        "newest_analysis": newest.strftime("%Y-%m-%d %H:%M"),
        "days_covered": (newest - oldest).days + 1,
    }


def print_history_summary():
    """Print a summary of the analysis history."""
    stats = get_history_stats()
    
    if not stats:
        print("No analysis history found.")
        return
    
    print("\n" + "=" * 75)
    print("  ANALYSIS HISTORY SUMMARY")
    print("=" * 75)
    print(f"  Total analyses saved: {stats['total_analyses']}")
    print(f"  Total bets recommended: {stats['total_bets_recommended']}")
    print(f"  Total games analyzed: {stats['total_games_analyzed']}")
    print(f"  Date range: {stats['oldest_analysis']} to {stats['newest_analysis']}")
    print(f"  Days covered: {stats['days_covered']}")
    print("=" * 75)


def export_bets_to_csv(output_path: str = "bet_history_export.csv", days_back: int = 30):
    """
    Export all bets from history to CSV for external analysis.
    
    Args:
        output_path: Path to save CSV file
        days_back: How many days back to export
    """
    import csv
    
    bets = get_all_bets_from_history(days_back)
    
    if not bets:
        print("No bets found in history.")
        return
    
    # Define CSV columns
    fieldnames = [
        "analysis_timestamp", "game", "pick", "bet_type", "book",
        "odds", "stake", "edge", "ev", "roi", "confidence",
        "true_prob", "implied_prob", "decimal_odds"
    ]
    
    with open(output_path, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        
        for bet in bets:
            writer.writerow(bet)
    
    print(f"✅ Exported {len(bets)} bets to {output_path}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Analysis History Manager")
    parser.add_argument("--summary", action="store_true",
                       help="Show history summary")
    parser.add_argument("--export", action="store_true",
                       help="Export bets to CSV")
    parser.add_argument("--days", type=int, default=30,
                       help="Days back to include (default: 30)")
    parser.add_argument("--output", type=str, default="bet_history_export.csv",
                       help="Output CSV filename")
    args = parser.parse_args()
    
    if args.summary:
        print_history_summary()
    elif args.export:
        export_bets_to_csv(args.output, args.days)
    else:
        print("Use --summary to view history or --export to export to CSV")
        print("Example: python analysis_history.py --summary")
        print("Example: python analysis_history.py --export --days 30")
