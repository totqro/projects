"""
Player-Level Data Fetcher
Fetches goalie stats, injuries, and key player information from NHL API.
"""

import requests
import json
from datetime import datetime
from pathlib import Path
import time

BASE_URL = "https://api-web.nhle.com/v1"
CACHE_DIR = Path(__file__).parent.parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)


def _get_cached(key: str, max_age_hours: int = 6):
    """Return cached JSON if fresh enough."""
    path = CACHE_DIR / f"{key}.json"
    if path.exists():
        age = time.time() - path.stat().st_mtime
        if age < max_age_hours * 3600:
            return json.loads(path.read_text())
    return None


def _set_cache(key: str, data):
    """Save data to cache."""
    path = CACHE_DIR / f"{key}.json"
    path.write_text(json.dumps(data, default=str))


def fetch_team_roster(team_abbrev: str, season: str = "20252026"):
    """
    Fetch team roster with player stats.
    Returns dict with forwards, defensemen, and goalies.
    """
    cache_key = f"roster_{team_abbrev}_{season}"
    cached = _get_cached(cache_key, max_age_hours=24)
    if cached:
        return cached
    
    try:
        url = f"{BASE_URL}/roster/{team_abbrev}/{season}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        roster = resp.json()
        
        _set_cache(cache_key, roster)
        return roster
    except Exception as e:
        print(f"  Warning: Could not fetch roster for {team_abbrev}: {e}")
        return {}


def get_goalie_stats(team_abbrev: str):
    """
    Get goalie statistics for a team.
    Returns list of goalies with their stats.
    """
    roster = fetch_team_roster(team_abbrev)
    
    goalies = []
    for goalie in roster.get("goalies", []):
        # Extract key stats
        goalie_info = {
            "name": goalie.get("firstName", {}).get("default", "") + " " + 
                   goalie.get("lastName", {}).get("default", ""),
            "number": goalie.get("sweaterNumber"),
            "id": goalie.get("id"),
        }
        goalies.append(goalie_info)
    
    return goalies


def fetch_player_stats(player_id: int, season: str = "20252026"):
    """
    Fetch detailed stats for a specific player.
    """
    cache_key = f"player_{player_id}_{season}"
    cached = _get_cached(cache_key, max_age_hours=24)
    if cached:
        return cached
    
    try:
        # Note: This endpoint might need adjustment based on NHL API structure
        url = f"{BASE_URL}/player/{player_id}/landing"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        stats = resp.json()
        
        _set_cache(cache_key, stats)
        return stats
    except Exception as e:
        print(f"  Warning: Could not fetch player {player_id} stats: {e}")
        return {}


def get_starting_goalie(team_abbrev: str, game_date: str = None):
    """
    Try to determine the starting goalie for a team.
    This is tricky - NHL doesn't always announce starters early.
    
    Returns best guess based on recent starts and rest days.
    """
    if game_date is None:
        game_date = datetime.now().strftime("%Y-%m-%d")
    
    goalies = get_goalie_stats(team_abbrev)
    
    # TODO: Enhance this with actual game logs to see who started recently
    # For now, return the list of goalies
    return goalies


def get_team_injuries(team_abbrev: str):
    """
    Get injury report for a team.
    Note: NHL API doesn't have a dedicated injuries endpoint.
    This would need to be scraped from other sources or manually updated.
    """
    # Placeholder - would need external data source
    return []


def extract_player_features(home_team: str, away_team: str):
    """
    Extract player-level features for ML model.
    
    Returns dict with:
    - Goalie stats (save %, GAA)
    - Top scorer stats
    - Injury impact
    - Back-to-back indicator
    """
    features = {
        "home_goalies": get_goalie_stats(home_team),
        "away_goalies": get_goalie_stats(away_team),
        "home_injuries": get_team_injuries(home_team),
        "away_injuries": get_team_injuries(away_team),
    }
    
    return features


def get_goalie_season_stats(team_abbrev: str, season: str = "20252026"):
    """
    Get aggregated goalie stats for the season.
    This would include save %, GAA, wins, etc.
    """
    # This would require accessing game-by-game logs
    # Placeholder for now
    return {
        "primary_goalie": {
            "save_pct": 0.910,  # League average
            "gaa": 2.80,
            "games_played": 0,
        },
        "backup_goalie": {
            "save_pct": 0.900,
            "gaa": 3.00,
            "games_played": 0,
        }
    }


def get_rest_days(team_abbrev: str, game_date: str):
    """
    Calculate days of rest before a game.
    Useful for fatigue analysis.
    """
    # Would need to look at team schedule
    # Placeholder
    return 1


def is_back_to_back(team_abbrev: str, game_date: str):
    """
    Check if team is playing back-to-back games.
    Teams typically perform worse on back-to-backs.
    """
    # Would need schedule data
    # Placeholder
    return False


# Example usage and testing
if __name__ == "__main__":
    print("Testing player data fetcher...")
    
    # Test roster fetch
    print("\nFetching TOR roster...")
    roster = fetch_team_roster("TOR")
    if roster:
        print(f"  Found {len(roster.get('forwards', []))} forwards")
        print(f"  Found {len(roster.get('defensemen', []))} defensemen")
        print(f"  Found {len(roster.get('goalies', []))} goalies")
    
    # Test goalie stats
    print("\nFetching TOR goalies...")
    goalies = get_goalie_stats("TOR")
    for g in goalies:
        print(f"  {g['name']} (#{g['number']})")
