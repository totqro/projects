"""
Goalie Tracker API
==================
Tracks starting goalies and their performance metrics.
Scrapes multiple sources and provides confidence-scored predictions.

Data Sources:
1. DailyFaceoff.com - Starting goalie confirmations
2. NHL API - Goalie season stats
3. Natural Stat Trick - Advanced goalie metrics (optional)

Usage:
    from goalie_tracker import get_todays_starters, get_goalie_quality_score
    
    starters = get_todays_starters()
    quality = get_goalie_quality_score("TOR", starters)
"""

import requests
from bs4 import BeautifulSoup
import json
from pathlib import Path
from datetime import datetime, timedelta
import time
import re

BASE_URL = "https://api-web.nhle.com/v1"
CACHE_DIR = Path(__file__).parent.parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)


def _get_cached(key: str, max_age_hours: int = 2):
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


# Team name mappings for different sources
TEAM_NAME_MAP = {
    # Full names to abbreviations
    "Anaheim Ducks": "ANA",
    "Arizona Coyotes": "ARI",
    "Boston Bruins": "BOS",
    "Buffalo Sabres": "BUF",
    "Calgary Flames": "CGY",
    "Carolina Hurricanes": "CAR",
    "Chicago Blackhawks": "CHI",
    "Colorado Avalanche": "COL",
    "Columbus Blue Jackets": "CBJ",
    "Dallas Stars": "DAL",
    "Detroit Red Wings": "DET",
    "Edmonton Oilers": "EDM",
    "Florida Panthers": "FLA",
    "Los Angeles Kings": "LAK",
    "Minnesota Wild": "MIN",
    "Montreal Canadiens": "MTL",
    "Montréal Canadiens": "MTL",
    "Nashville Predators": "NSH",
    "New Jersey Devils": "NJD",
    "New York Islanders": "NYI",
    "New York Rangers": "NYR",
    "Ottawa Senators": "OTT",
    "Philadelphia Flyers": "PHI",
    "Pittsburgh Penguins": "PIT",
    "San Jose Sharks": "SJS",
    "Seattle Kraken": "SEA",
    "St. Louis Blues": "STL",
    "Tampa Bay Lightning": "TBL",
    "Toronto Maple Leafs": "TOR",
    "Utah Hockey Club": "UTA",
    "Vancouver Canucks": "VAN",
    "Vegas Golden Knights": "VGK",
    "Washington Capitals": "WSH",
    "Winnipeg Jets": "WPG",
    # Short names
    "Ducks": "ANA",
    "Coyotes": "ARI",
    "Bruins": "BOS",
    "Sabres": "BUF",
    "Flames": "CGY",
    "Hurricanes": "CAR",
    "Blackhawks": "CHI",
    "Avalanche": "COL",
    "Blue Jackets": "CBJ",
    "Stars": "DAL",
    "Red Wings": "DET",
    "Oilers": "EDM",
    "Panthers": "FLA",
    "Kings": "LAK",
    "Wild": "MIN",
    "Canadiens": "MTL",
    "Predators": "NSH",
    "Devils": "NJD",
    "Islanders": "NYI",
    "Rangers": "NYR",
    "Senators": "OTT",
    "Flyers": "PHI",
    "Penguins": "PIT",
    "Sharks": "SJS",
    "Kraken": "SEA",
    "Blues": "STL",
    "Lightning": "TBL",
    "Maple Leafs": "TOR",
    "Canucks": "VAN",
    "Golden Knights": "VGK",
    "Capitals": "WSH",
    "Jets": "WPG",
}


def normalize_team_name(name: str) -> str:
    """Convert any team name format to abbreviation."""
    name = name.strip()
    
    # Direct match
    if name in TEAM_NAME_MAP:
        return TEAM_NAME_MAP[name]
    
    # Try to find partial match
    for full_name, abbrev in TEAM_NAME_MAP.items():
        if name.lower() in full_name.lower() or full_name.lower() in name.lower():
            return abbrev
    
    # If already an abbreviation
    if len(name) == 3 and name.upper() in ["ANA", "ARI", "BOS", "BUF", "CGY", "CAR", "CHI", "COL", "CBJ", "DAL", "DET", "EDM", "FLA", "LAK", "MIN", "MTL", "NSH", "NJD", "NYI", "NYR", "OTT", "PHI", "PIT", "SJS", "SEA", "STL", "TBL", "TOR", "UTA", "VAN", "VGK", "WSH", "WPG"]:
        return name.upper()
    
    return name  # Return as-is if can't normalize


def scrape_dailyfaceoff_goalies(date_str=None):
    """
    Scrape starting goalies from DailyFaceoff.com
    
    Returns dict: {
        team_abbrev: {
            'name': str,
            'status': 'confirmed' | 'likely' | 'probable' | 'unknown',
            'confidence': float (0-1),
            'source': 'dailyfaceoff',
            'last_updated': timestamp
        }
    }
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    cache_key = f"dailyfaceoff_goalies_{date_str}"
    cached = _get_cached(cache_key, max_age_hours=2)
    if cached:
        return cached
    
    goalies = {}
    
    try:
        url = "https://www.dailyfaceoff.com/starting-goalies/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        print("  Scraping DailyFaceoff for starting goalies...")
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # DailyFaceoff 2026: Structure is:
        # Line: "Away Team at Home Team Mar DD, YYYY | H:MM pm EDT"
        # Next few lines: Away goalie name, status, timestamp, "SHOW MORE", ranking, links...
        # After "Schedule": Home goalie name, status, timestamp, "SHOW MORE", ranking, links...
        
        page_text = soup.get_text('\n')
        lines = [line.strip() for line in page_text.split('\n') if line.strip()]
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Check if this line contains " at " (game matchup)
            if ' at ' in line and ('Mar' in line or 'pm EDT' in line or 'am EDT' in line):
                # Extract team names
                # Format: "Away Team at Home Team Mar DD, YYYY | H:MM pm EDT"
                match = re.match(r'^(.+?)\s+at\s+(.+?)\s+(?:Mar|Apr|Oct|Nov|Dec|Jan|Feb)', line)
                
                if match:
                    away_team_name = match.group(1).strip()
                    home_team_name = match.group(2).strip()
                    
                    away_abbrev = normalize_team_name(away_team_name)
                    home_abbrev = normalize_team_name(home_team_name)
                    
                    # Look for away goalie (next few lines after matchup)
                    away_goalie = None
                    home_goalie = None
                    found_schedule = False
                    
                    for j in range(i+1, min(i+40, len(lines))):
                        check_line = lines[j]
                        
                        # Check if this is a goalie name (2+ capitalized words)
                        name_match = re.match(r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)$', check_line)
                        
                        if name_match and j+1 < len(lines):
                            goalie_name = name_match.group(1)
                            next_line = lines[j+1]
                            
                            # Check if next line is a status
                            if re.match(r'^(Confirmed|Likely|Probable|Expected|Unconfirmed)', next_line, re.I):
                                status_text = next_line.lower()
                                
                                # Determine confidence
                                if 'confirm' in status_text:
                                    status = 'confirmed'
                                    confidence = 1.0
                                elif 'likely' in status_text:
                                    status = 'likely'
                                    confidence = 0.8
                                elif 'probable' in status_text or 'expected' in status_text:
                                    status = 'probable'
                                    confidence = 0.7
                                else:
                                    status = 'unconfirmed'
                                    confidence = 0.5
                                
                                goalie_info = {
                                    'name': goalie_name,
                                    'status': status,
                                    'confidence': confidence,
                                    'source': 'dailyfaceoff',
                                    'last_updated': datetime.now().isoformat()
                                }
                                
                                # Assign to away or home based on whether we've seen "Schedule" yet
                                if not found_schedule and not away_goalie:
                                    away_goalie = goalie_info
                                elif found_schedule and not home_goalie:
                                    home_goalie = goalie_info
                                    break  # Found both goalies for this game
                        
                        # Check if we've reached the "Schedule" marker (separates away/home)
                        if check_line == 'Schedule':
                            found_schedule = True
                    
                    # Assign goalies to teams
                    if away_goalie and away_abbrev:
                        goalies[away_abbrev] = away_goalie
                    if home_goalie and home_abbrev:
                        goalies[home_abbrev] = home_goalie
            
            i += 1
        
        print(f"  ✅ Found {len(goalies)} starting goalies from DailyFaceoff")
        
    except Exception as e:
        print(f"  ⚠️  Could not scrape DailyFaceoff: {e}")
    
    _set_cache(cache_key, goalies)
    return goalies


def fetch_goalie_stats_nhl_api(team_abbrev: str, season: str = "20252026"):
    """
    Fetch goalie stats from NHL API for a team.
    
    Returns list of goalies with season stats AND recent form (last 10 starts).
    """
    cache_key = f"goalie_stats_{team_abbrev}_{season}"
    cached = _get_cached(cache_key, max_age_hours=24)
    if cached:
        return cached
    
    try:
        # Get team roster
        url = f"{BASE_URL}/roster/{team_abbrev}/{season}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        roster = resp.json()
        
        goalies = []
        for goalie in roster.get("goalies", []):
            goalie_id = goalie.get("id")
            
            # Get detailed stats for this goalie
            try:
                stats_url = f"{BASE_URL}/player/{goalie_id}/landing"
                stats_resp = requests.get(stats_url, timeout=10)
                stats_resp.raise_for_status()
                stats_data = stats_resp.json()
                
                # Extract current season stats
                season_stats = stats_data.get("featuredStats", {}).get("regularSeason", {}).get("subSeason", {})
                
                # Get game log for recent form
                recent_form = _fetch_goalie_recent_form(goalie_id, season)
                
                goalie_info = {
                    "id": goalie_id,
                    "name": f"{goalie.get('firstName', {}).get('default', '')} {goalie.get('lastName', {}).get('default', '')}",
                    "number": goalie.get("sweaterNumber"),
                    "games_played": season_stats.get("gamesPlayed", 0),
                    "wins": season_stats.get("wins", 0),
                    "losses": season_stats.get("losses", 0),
                    "ot_losses": season_stats.get("otLosses", 0),
                    "save_pct": season_stats.get("savePctg", 0.900),
                    "gaa": season_stats.get("goalsAgainstAvg", 3.00),
                    "shutouts": season_stats.get("shutouts", 0),
                    "goals_against": season_stats.get("goalsAgainst", 0),
                    "shots_against": season_stats.get("shotsAgainst", 0),
                    "saves": season_stats.get("saves", 0),
                    # Recent form (last 10 starts)
                    "recent_save_pct": recent_form.get("save_pct", 0.900),
                    "recent_gaa": recent_form.get("gaa", 3.00),
                    "recent_quality_starts": recent_form.get("quality_starts", 0),
                    "recent_games": recent_form.get("games", 0),
                }
                
                goalies.append(goalie_info)
                time.sleep(0.1)  # Rate limiting
                
            except Exception as e:
                # If can't get detailed stats, add basic info
                goalies.append({
                    "id": goalie_id,
                    "name": f"{goalie.get('firstName', {}).get('default', '')} {goalie.get('lastName', {}).get('default', '')}",
                    "number": goalie.get("sweaterNumber"),
                    "games_played": 0,
                    "save_pct": 0.900,
                    "gaa": 3.00,
                    "recent_save_pct": 0.900,
                    "recent_gaa": 3.00,
                    "recent_quality_starts": 0,
                    "recent_games": 0,
                })
        
        _set_cache(cache_key, goalies)
        return goalies
        
    except Exception as e:
        print(f"  ⚠️  Could not fetch goalie stats for {team_abbrev}: {e}")
        return []
def _fetch_goalie_recent_form(goalie_id: int, season: str = "20252026", n_games: int = 10):
    """
    Fetch recent form for a goalie (last n starts).

    Returns dict with:
    - save_pct: Save % in last n games
    - gaa: GAA in last n games
    - quality_starts: Number of quality starts (SV% > .900)
    - games: Number of games in sample
    """
    cache_key = f"goalie_recent_{goalie_id}_{season}_{n_games}"
    cached = _get_cached(cache_key, max_age_hours=6)
    if cached:
        return cached

    try:
        # Fetch game log
        url = f"{BASE_URL}/player/{goalie_id}/game-log/{season}/2"  # 2 = regular season
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        game_log = resp.json()

        # Get last n games
        games = game_log.get("gameLog", [])[:n_games]

        if not games:
            return {
                "save_pct": 0.900,
                "gaa": 3.00,
                "quality_starts": 0,
                "games": 0
            }

        total_saves = 0
        total_shots = 0
        total_goals_against = 0
        total_toi_minutes = 0
        quality_starts = 0

        for game in games:
            shots_against = game.get("shotsAgainst", 0)
            goals_against = game.get("goalsAgainst", 0)
            saves = shots_against - goals_against  # Calculate saves
            toi = game.get("toi", "0:00")

            # Parse TOI (format: "MM:SS")
            try:
                if ":" in toi:
                    parts = toi.split(":")
                    minutes = int(parts[0]) + int(parts[1]) / 60
                else:
                    minutes = 0
            except:
                minutes = 0

            total_saves += saves
            total_shots += shots_against
            total_goals_against += goals_against
            total_toi_minutes += minutes

            # Quality start = SV% > .900 (or < 3 goals against in full game)
            if shots_against > 0:
                game_sv_pct = saves / shots_against
                if game_sv_pct > 0.900:
                    quality_starts += 1

        # Calculate averages
        save_pct = total_saves / total_shots if total_shots > 0 else 0.900

        # GAA = (goals_against * 60) / total_minutes
        gaa = (total_goals_against * 60) / total_toi_minutes if total_toi_minutes > 0 else 3.00

        result = {
            "save_pct": round(save_pct, 3),
            "gaa": round(gaa, 2),
            "quality_starts": quality_starts,
            "games": len(games)
        }

        _set_cache(cache_key, result)
        return result

    except Exception as e:
        # Return defaults if can't fetch
        return {
            "save_pct": 0.900,
            "gaa": 3.00,
            "quality_starts": 0,
            "games": 0
        }





def get_goalie_quality_score(goalie_stats: dict) -> float:
    """
    Calculate a quality score for a goalie (0-100).
    
    Factors:
    - Save percentage (most important)
    - GAA
    - Games played (experience)
    - Win percentage
    
    Returns:
        float: Quality score 0-100 (50 = league average)
    """
    if not goalie_stats:
        return 50.0  # Default to average
    
    # League averages (2024-25 season)
    AVG_SAVE_PCT = 0.900
    AVG_GAA = 2.90
    
    save_pct = goalie_stats.get("save_pct", AVG_SAVE_PCT)
    gaa = goalie_stats.get("gaa", AVG_GAA)
    games_played = goalie_stats.get("games_played", 0)
    wins = goalie_stats.get("wins", 0)
    
    # Calculate components
    # Save % is most important (60% weight)
    save_pct_score = ((save_pct - AVG_SAVE_PCT) / 0.030) * 30 + 50  # ±0.030 = ±30 points
    save_pct_score = max(0, min(100, save_pct_score))
    
    # GAA (30% weight) - lower is better
    gaa_score = ((AVG_GAA - gaa) / 1.0) * 15 + 50  # ±1.0 GAA = ±15 points
    gaa_score = max(0, min(100, gaa_score))
    
    # Experience bonus (10% weight)
    if games_played >= 40:
        experience_score = 60
    elif games_played >= 20:
        experience_score = 55
    elif games_played >= 10:
        experience_score = 50
    else:
        experience_score = 40  # Penalty for inexperience
    
    # Win percentage (if enough games)
    if games_played > 0:
        win_pct = wins / games_played
        win_score = win_pct * 100
    else:
        win_score = 50
    
    # Weighted average
    quality_score = (
        save_pct_score * 0.60 +
        gaa_score * 0.30 +
        experience_score * 0.05 +
        win_score * 0.05
    )
    
    return round(quality_score, 1)


def get_todays_starters(date_str=None):
    """
    Get starting goalies for today's games with quality scores.
    
    Returns dict: {
        team_abbrev: {
            'starter': {
                'name': str,
                'status': str,
                'confidence': float,
                'quality_score': float,
                'stats': dict
            },
            'backup': {
                'name': str,
                'quality_score': float,
                'stats': dict
            }
        }
    }
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    cache_key = f"todays_starters_{date_str}"
    cached = _get_cached(cache_key, max_age_hours=2)
    if cached:
        return cached
    
    print("\n[Goalie Tracker] Fetching starting goalies...")
    
    # Get confirmed starters from DailyFaceoff
    confirmed_starters = scrape_dailyfaceoff_goalies(date_str)
    
    # Get all goalie stats from NHL API
    from src.data.nhl_data import NHL_TEAMS
    
    all_starters = {}
    
    for team in NHL_TEAMS:
        try:
            # Get team's goalies and their stats
            goalies = fetch_goalie_stats_nhl_api(team)
            
            if not goalies:
                continue
            
            # Sort by games played (primary starter first)
            goalies.sort(key=lambda g: g.get("games_played", 0), reverse=True)
            
            primary = goalies[0] if len(goalies) > 0 else None
            backup = goalies[1] if len(goalies) > 1 else None
            
            # Check if we have confirmed starter from DailyFaceoff
            confirmed = confirmed_starters.get(team, {})
            
            # Determine who's starting
            if confirmed:
                # Match confirmed name to our goalie list
                confirmed_name = confirmed['name'].lower()
                starter = None
                
                for g in goalies:
                    if confirmed_name in g['name'].lower() or g['name'].lower() in confirmed_name:
                        starter = g
                        break
                
                if not starter:
                    starter = primary  # Fallback to primary
                
                starter_info = {
                    'name': starter['name'],
                    'status': confirmed['status'],
                    'confidence': confirmed['confidence'],
                    'quality_score': get_goalie_quality_score(starter),
                    'stats': starter
                }
            else:
                # No confirmation, assume primary starter
                if primary:
                    starter_info = {
                        'name': primary['name'],
                        'status': 'probable',
                        'confidence': 0.7,  # Educated guess
                        'quality_score': get_goalie_quality_score(primary),
                        'stats': primary
                    }
                else:
                    continue
            
            # Add backup info
            backup_info = None
            if backup:
                backup_info = {
                    'name': backup['name'],
                    'quality_score': get_goalie_quality_score(backup),
                    'stats': backup
                }
            
            all_starters[team] = {
                'starter': starter_info,
                'backup': backup_info
            }
            
            time.sleep(0.1)  # Rate limiting
            
        except Exception as e:
            print(f"  ⚠️  Error processing {team}: {e}")
            continue
    
    print(f"  ✅ Processed {len(all_starters)} teams")
    
    _set_cache(cache_key, all_starters)
    return all_starters


def get_goalie_matchup_analysis(home_team: str, away_team: str, date_str=None):
    """
    Analyze goalie matchup for a specific game.
    
    Returns dict with:
    - home_goalie: starter info + quality score
    - away_goalie: starter info + quality score
    - advantage: 'home' | 'away' | 'even'
    - advantage_score: float (-100 to +100, positive = home advantage)
    """
    starters = get_todays_starters(date_str)
    
    home_goalie = starters.get(home_team, {}).get('starter')
    away_goalie = starters.get(away_team, {}).get('starter')
    
    if not home_goalie or not away_goalie:
        return {
            'home_goalie': home_goalie,
            'away_goalie': away_goalie,
            'advantage': 'unknown',
            'advantage_score': 0,
            'confidence': 0.5
        }
    
    home_quality = home_goalie['quality_score']
    away_quality = away_goalie['quality_score']
    
    advantage_score = home_quality - away_quality
    
    if advantage_score > 10:
        advantage = 'home'
    elif advantage_score < -10:
        advantage = 'away'
    else:
        advantage = 'even'
    
    # Overall confidence is minimum of both goalies' confirmation confidence
    confidence = min(home_goalie['confidence'], away_goalie['confidence'])
    
    return {
        'home_goalie': home_goalie,
        'away_goalie': away_goalie,
        'advantage': advantage,
        'advantage_score': advantage_score,
        'confidence': confidence
    }


if __name__ == "__main__":
    print("=" * 80)
    print("  GOALIE TRACKER TEST")
    print("=" * 80)
    
    # Test getting today's starters
    starters = get_todays_starters()
    
    print(f"\nFound starters for {len(starters)} teams:\n")
    
    for team, info in sorted(starters.items()):
        starter = info['starter']
        print(f"{team:4s} | {starter['name']:25s} | "
              f"Quality: {starter['quality_score']:5.1f} | "
              f"Status: {starter['status']:10s} | "
              f"Confidence: {starter['confidence']:.0%}")
    
    # Test matchup analysis
    print("\n" + "=" * 80)
    print("  SAMPLE MATCHUP ANALYSIS")
    print("=" * 80)
    
    # Pick first two teams as example
    teams = list(starters.keys())
    if len(teams) >= 2:
        home = teams[0]
        away = teams[1]
        
        matchup = get_goalie_matchup_analysis(home, away)
        
        print(f"\n{away} @ {home}")
        print(f"\nHome Goalie ({home}):")
        print(f"  {matchup['home_goalie']['name']}")
        print(f"  Quality Score: {matchup['home_goalie']['quality_score']:.1f}")
        print(f"  SV%: {matchup['home_goalie']['stats']['save_pct']:.3f}")
        print(f"  GAA: {matchup['home_goalie']['stats']['gaa']:.2f}")
        
        print(f"\nAway Goalie ({away}):")
        print(f"  {matchup['away_goalie']['name']}")
        print(f"  Quality Score: {matchup['away_goalie']['quality_score']:.1f}")
        print(f"  SV%: {matchup['away_goalie']['stats']['save_pct']:.3f}")
        print(f"  GAA: {matchup['away_goalie']['stats']['gaa']:.2f}")
        
        print(f"\nAdvantage: {matchup['advantage'].upper()}")
        print(f"Advantage Score: {matchup['advantage_score']:+.1f}")
        print(f"Confidence: {matchup['confidence']:.0%}")
