"""
Analysis History Manager
Saves all analysis outputs, removes duplicates, maintains 30-day rolling history.
"""

import json
from pathlib import Path
from datetime import datetime, timedelta, timezone


HISTORY_PATH = Path(__file__).parent.parent.parent / "mlbdata" / "analysis_history.json"
MAX_DAYS = 30


def _parse_timestamp(ts_str):
    dt = datetime.fromisoformat(ts_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def save_analysis(analysis_data):
    """Save analysis to history with deduplication and rolling window."""
    if HISTORY_PATH.exists():
        history = json.loads(HISTORY_PATH.read_text())
    else:
        history = {"analyses": []}

    if "timestamp" not in analysis_data:
        analysis_data["timestamp"] = datetime.now(timezone.utc).isoformat()

    new_timestamp = _parse_timestamp(analysis_data["timestamp"])

    def get_analysis_signature(analysis):
        recs = analysis.get("recommendations", [])
        if not recs:
            return None
        sig_parts = []
        for rec in sorted(recs, key=lambda r: (r.get("game", ""), r.get("pick", ""))):
            sig_parts.append(f"{rec.get('game', '')}_{rec.get('pick', '')}")
        return "|".join(sig_parts)

    new_sig = get_analysis_signature(analysis_data)
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=MAX_DAYS)
    filtered = []

    for existing in history["analyses"]:
        existing_time = _parse_timestamp(existing["timestamp"])
        if existing_time < cutoff_date:
            continue
        if new_sig and get_analysis_signature(existing) == new_sig:
            continue
        time_diff = abs((existing_time - new_timestamp).total_seconds())
        if time_diff < 300:
            continue
        filtered.append(existing)

    filtered.append(analysis_data)
    filtered.sort(key=lambda x: x["timestamp"], reverse=True)

    history["analyses"] = filtered
    history["last_updated"] = datetime.now(timezone.utc).isoformat()
    history["total_analyses"] = len(filtered)

    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(history, indent=2, default=str))
    print(f"  Saved to history ({len(filtered)} analyses in last {MAX_DAYS} days)")


def get_all_bets_from_history(days_back=30):
    """Get all bets from historical analyses."""
    if not HISTORY_PATH.exists():
        return []

    history = json.loads(HISTORY_PATH.read_text())
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

    all_bets = []
    for analysis in history["analyses"]:
        analysis_time = _parse_timestamp(analysis["timestamp"])
        if analysis_time < cutoff:
            continue
        if "recommendations" in analysis:
            for bet in analysis["recommendations"]:
                all_bets.append({**bet, "analysis_timestamp": analysis["timestamp"]})

    return all_bets


def get_history_stats(days_back=30):
    """Get statistics about the analysis history."""
    if not HISTORY_PATH.exists():
        return None

    history = json.loads(HISTORY_PATH.read_text())
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

    recent = [a for a in history["analyses"]
              if _parse_timestamp(a["timestamp"]) >= cutoff]

    if not recent:
        return None

    total_bets = sum(len(a.get("recommendations", [])) for a in recent)
    total_games = sum(len(a.get("games_analyzed", [])) for a in recent)

    timestamps = [datetime.fromisoformat(a["timestamp"]) for a in recent]
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
