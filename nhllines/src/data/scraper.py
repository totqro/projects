"""
Web Scraper for Free NHL Data
Scrapes starting goalies, injuries, and schedule info from free sources.
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import json
from pathlib import Path
import time

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


def scrape_daily_faceoff_goalies(date_str=None):
    """
    Scrape starting goalies from Daily Faceoff.
    Free source, updates throughout the day.
    
    Returns dict: {team_abbrev: {name, confirmed, stats}}
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    cache_key = f"starting_goalies_{date_str}"
    cached = _get_cached(cache_key, max_age_hours=2)
    if cached:
        return cached
    
    try:
        url = "https://www.dailyfaceoff.com/starting-goalies/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        goalies = {}
        
        # Find goalie cards (structure may vary, this is a template)
        goalie_cards = soup.find_all('div', class_='starting-goalies-card')
        
        for card in goalie_cards:
            try:
                # Extract team (adjust selectors based on actual HTML)
                team_elem = card.find('span', class_='team-name')
                if not team_elem:
                    continue
                
                team = team_elem.text.strip()
                
                # Extract goalie name
                name_elem = card.find('a', class_='goalie-name')
                if not name_elem:
                    continue
                
                name = name_elem.text.strip()
                
                # Check if confirmed
                status_elem = card.find('span', class_='status')
                confirmed = 'confirmed' in status_elem.text.lower() if status_elem else False
                
                # Extract stats if available
                stats = {}
                stats_elem = card.find('div', class_='goalie-stats')
                if stats_elem:
                    # Parse stats (GAA, SV%, etc.)
                    pass
                
                goalies[team] = {
                    'name': name,
                    'confirmed': confirmed,
                    'stats': stats
                }
            except Exception as e:
                continue
        
        _set_cache(cache_key, goalies)
        return goalies
        
    except Exception as e:
        print(f"  Warning: Could not scrape Daily Faceoff: {e}")
        return {}


def scrape_nhl_injuries():
    """
    Scrape injury reports from NHL.com or other free sources.
    
    Returns dict: {team_abbrev: [{player, position, injury, status}]}
    """
    cache_key = "injuries_current"
    cached = _get_cached(cache_key, max_age_hours=12)
    if cached:
        return cached
    
    try:
        # NHL.com doesn't have a great injuries page
        # Alternative: Use ESPN or other free source
        url = "https://www.espn.com/nhl/injuries"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        injuries = {}
        
        # Parse injury tables (structure varies by site)
        # This is a template - adjust based on actual HTML
        
        _set_cache(cache_key, injuries)
        return injuries
        
    except Exception as e:
        print(f"  Warning: Could not scrape injuries: {e}")
        return {}


def get_team_schedule_from_nhl_api(team_abbrev: str, days_back=7, days_forward=7):
    """
    Get team schedule from NHL API to determine back-to-backs and rest days.
    Free NHL API endpoint.
    """
    cache_key = f"schedule_{team_abbrev}_{days_back}_{days_forward}"
    cached = _get_cached(cache_key, max_age_hours=24)
    if cached:
        return cached
    
    try:
        # Calculate date range
        today = datetime.now()
        start_date = (today - timedelta(days=days_back)).strftime("%Y-%m-%d")
        end_date = (today + timedelta(days=days_forward)).strftime("%Y-%m-%d")
        
        # NHL API schedule endpoint
        url = f"https://api-web.nhle.com/v1/club-schedule/{team_abbrev}/week/now"
        
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        schedule = resp.json()
        
        _set_cache(cache_key, schedule)
        return schedule
        
    except Exception as e:
        print(f"  Warning: Could not fetch schedule for {team_abbrev}: {e}")
        return {}


def calculate_rest_days(team_abbrev: str, game_date: str):
    """
    Calculate days of rest before a game.
    
    Returns:
        int: Number of days since last game (0 = back-to-back)
    """
    schedule = get_team_schedule_from_nhl_api(team_abbrev)
    
    if not schedule or 'games' not in schedule:
        return 1  # Default assumption
    
    games = schedule.get('games', [])
    game_dates = []
    
    for game in games:
        game_date_str = game.get('gameDate', '')[:10]
        if game_date_str:
            game_dates.append(game_date_str)
    
    game_dates.sort()
    
    # Find the game before our target date
    target = datetime.strptime(game_date, "%Y-%m-%d")
    
    previous_game = None
    for gd in game_dates:
        gd_dt = datetime.strptime(gd, "%Y-%m-%d")
        if gd_dt < target:
            previous_game = gd_dt
        elif gd_dt >= target:
            break
    
    if previous_game:
        rest_days = (target - previous_game).days - 1
        return max(0, rest_days)
    
    return 1  # Default


def is_back_to_back(team_abbrev: str, game_date: str):
    """
    Check if team is playing back-to-back games.
    
    Returns:
        bool: True if playing on consecutive days
    """
    rest_days = calculate_rest_days(team_abbrev, game_date)
    return rest_days == 0


def get_goalie_stats_from_nhl(goalie_name: str, team_abbrev: str):
    """
    Get goalie season stats from NHL API.
    Free endpoint with detailed stats.
    """
    cache_key = f"goalie_stats_{goalie_name.replace(' ', '_')}_{team_abbrev}"
    cached = _get_cached(cache_key, max_age_hours=24)
    if cached:
        return cached
    
    try:
        # This would require knowing the goalie's player ID
        # For now, return defaults
        stats = {
            'save_pct': 0.910,
            'gaa': 2.80,
            'wins': 0,
            'games_played': 0,
        }
        
        _set_cache(cache_key, stats)
        return stats
        
    except Exception as e:
        print(f"  Warning: Could not fetch goalie stats: {e}")
        return {'save_pct': 0.910, 'gaa': 2.80, 'wins': 0, 'games_played': 0}


def assess_injury_impact(injuries: list):
    """
    Assess the impact of injuries on team performance.
    
    Returns:
        int: 0 = no impact, 1 = minor, 2 = significant, 3 = star player out
    """
    if not injuries:
        return 0
    
    # Keywords for star players
    star_keywords = ['out', 'ir', 'ltir', 'week-to-week', 'month-to-month']
    
    max_impact = 0
    for injury in injuries:
        status = injury.get('status', '').lower()
        position = injury.get('position', '').lower()
        
        # Check if it's a serious injury
        if any(keyword in status for keyword in star_keywords):
            if 'center' in position or 'forward' in position:
                max_impact = max(max_impact, 2)
            elif 'defense' in position:
                max_impact = max(max_impact, 2)
            elif 'goalie' in position:
                max_impact = max(max_impact, 3)  # Goalie injuries are huge
    
    return max_impact


# Simplified scraper that uses NHL API only (most reliable)
def get_player_data_nhl_api_only(home_team: str, away_team: str, game_date: str):
    """
    Get all player data using only the free NHL API.
    Most reliable approach - no web scraping needed.
    
    OPTIMIZED: Caches per-team data to avoid redundant API calls.
    
    Returns dict with:
    - rest_days for both teams
    - back_to_back indicators
    - basic goalie info
    """
    # Use per-team caching to avoid duplicate calls when same team plays multiple games
    cache_key = f"player_data_{home_team}_{away_team}_{game_date}"
    cached = _get_cached(cache_key, max_age_hours=12)
    if cached:
        return cached
    
    data = {
        'home_rest_days': calculate_rest_days(home_team, game_date),
        'away_rest_days': calculate_rest_days(away_team, game_date),
        'home_back_to_back': is_back_to_back(home_team, game_date),
        'away_back_to_back': is_back_to_back(away_team, game_date),
        'home_goalie_stats': {'save_pct': 0.910, 'gaa': 2.80},  # Defaults
        'away_goalie_stats': {'save_pct': 0.910, 'gaa': 2.80},
        'home_injury_impact': 0,
        'away_injury_impact': 0,
    }
    
    _set_cache(cache_key, data)
    return data


if __name__ == "__main__":
    print("Testing scrapers...")
    
    # Test schedule/rest days
    print("\nTesting rest days calculation...")
    today = datetime.now().strftime("%Y-%m-%d")
    rest = calculate_rest_days("TOR", today)
    b2b = is_back_to_back("TOR", today)
    print(f"  TOR rest days: {rest}")
    print(f"  TOR back-to-back: {b2b}")
    
    # Test player data fetch
    print("\nTesting player data fetch...")
    data = get_player_data_nhl_api_only("TOR", "BOS", today)
    print(f"  Data: {json.dumps(data, indent=2)}")
