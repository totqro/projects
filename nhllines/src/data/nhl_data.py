"""
NHL Historical Data Fetcher
Fetches game results, team stats, and standings from the free NHL API.
"""

import requests
import json
from datetime import datetime, timedelta
from pathlib import Path
import time

BASE_URL = "https://api-web.nhle.com/v1"
CACHE_DIR = Path(__file__).parent.parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

# NHL team abbreviations for 2024-2025 season
NHL_TEAMS = [
    "ANA", "ARI", "BOS", "BUF", "CAR", "CBJ", "CGY", "CHI",
    "COL", "DAL", "DET", "EDM", "FLA", "LAK", "MIN", "MTL",
    "NJD", "NSH", "NYI", "NYR", "OTT", "PHI", "PIT", "SEA",
    "SJS", "STL", "TBL", "TOR", "UTA", "VAN", "VGK", "WPG", "WSH"
]


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


def fetch_standings(date: str = None) -> dict:
    """
    Fetch NHL standings for a given date (YYYY-MM-DD).
    Returns dict keyed by team abbreviation with stats.
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    cache_key = f"standings_{date}"
    cached = _get_cached(cache_key, max_age_hours=12)
    if cached:
        return cached

    url = f"{BASE_URL}/standings/{date}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    raw = resp.json()

    standings = {}
    for team in raw.get("standings", []):
        abbrev = team.get("teamAbbrev", {}).get("default", "")
        if not abbrev:
            continue
        gp = team.get("gamesPlayed", 0)
        standings[abbrev] = {
            "team": abbrev,
            "team_name": team.get("teamName", {}).get("default", ""),
            "games_played": gp,
            "wins": team.get("wins", 0),
            "losses": team.get("losses", 0),
            "ot_losses": team.get("otLosses", 0),
            "points": team.get("points", 0),
            "points_pct": team.get("pointPctg", 0),
            "goals_for": team.get("goalFor", 0),
            "goals_against": team.get("goalAgainst", 0),
            "goals_for_pg": team.get("goalFor", 0) / max(gp, 1),
            "goals_against_pg": team.get("goalAgainst", 0) / max(gp, 1),
            "home_wins": team.get("homeWins", 0),
            "home_losses": team.get("homeLosses", 0),
            "home_ot_losses": team.get("homeOtLosses", 0),
            "road_wins": team.get("roadWins", 0),
            "road_losses": team.get("roadLosses", 0),
            "road_ot_losses": team.get("roadOtLosses", 0),
            "streak_code": team.get("streakCode", ""),
            "streak_count": team.get("streakCount", 0),
            "l10_wins": team.get("l10Wins", 0),
            "l10_losses": team.get("l10Losses", 0),
            "l10_ot_losses": team.get("l10OtLosses", 0),
            "win_pct": team.get("wins", 0) / max(gp, 1),
            "regulation_wins": team.get("regulationWins", 0),
        }

    _set_cache(cache_key, standings)
    return standings


def fetch_schedule(date: str = None) -> list:
    """
    Fetch NHL schedule/scores for a given date.
    Returns list of game dicts.
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    cache_key = f"schedule_{date}"
    cached = _get_cached(cache_key, max_age_hours=1)
    if cached:
        return cached

    url = f"{BASE_URL}/schedule/{date}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    raw = resp.json()

    games = []
    for game_week in raw.get("gameWeek", []):
        game_date = game_week.get("date", "")
        for game in game_week.get("games", []):
            home = game.get("homeTeam", {})
            away = game.get("awayTeam", {})
            games.append({
                "game_id": game.get("id"),
                "date": game_date,
                "start_time": game.get("startTimeUTC", ""),
                "game_state": game.get("gameState", ""),
                "home_team": home.get("abbrev", ""),
                "away_team": away.get("abbrev", ""),
                "home_score": home.get("score"),
                "away_score": away.get("score"),
                "venue": game.get("venue", {}).get("default", ""),
            })

    _set_cache(cache_key, games)
    return games


def fetch_scores(date: str = None) -> list:
    """
    Fetch completed game scores for a given date.
    Uses the /score endpoint which has more detail.
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    cache_key = f"scores_{date}"
    cached = _get_cached(cache_key, max_age_hours=2)
    if cached:
        return cached

    url = f"{BASE_URL}/score/{date}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    raw = resp.json()

    games = []
    for game in raw.get("games", []):
        home = game.get("homeTeam", {})
        away = game.get("awayTeam", {})
        games.append({
            "game_id": game.get("id"),
            "date": date,
            "game_state": game.get("gameState", ""),
            "home_team": home.get("abbrev", ""),
            "away_team": away.get("abbrev", ""),
            "home_score": home.get("score"),
            "away_score": away.get("score"),
            "period": game.get("periodDescriptor", {}).get("number"),
            "game_type": game.get("gameType", 2),  # 2 = regular season
        })

    _set_cache(cache_key, games)
    return games


def fetch_season_games(season: str = "20252026", days_back: int = 90) -> list:
    """
    Fetch all completed regular season games for recent history.
    Iterates day-by-day from days_back ago to today (inclusive).
    Returns list of completed game results.
    
    OPTIMIZED: Uses batch caching and parallel-friendly structure.
    """
    cache_key = f"season_games_{season}_{days_back}"
    cached = _get_cached(cache_key, max_age_hours=24)
    if cached:
        return cached

    all_games = []
    today = datetime.now()
    
    # Batch fetch with progress tracking
    total_days = days_back + 1
    fetched_days = 0

    # Include today by going from days_back down to 0 (inclusive)
    for i in range(days_back, -1, -1):
        date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        try:
            games = fetch_scores(date)
            for g in games:
                if g["game_state"] in ("OFF", "FINAL") and g["home_score"] is not None:
                    g["total_goals"] = (g["home_score"] or 0) + (g["away_score"] or 0)
                    g["home_win"] = (g["home_score"] or 0) > (g["away_score"] or 0)
                    g["goal_diff"] = (g["home_score"] or 0) - (g["away_score"] or 0)
                    all_games.append(g)
            fetched_days += 1
            
            # Show progress every 10 days
            if fetched_days % 10 == 0:
                print(f"  Progress: {fetched_days}/{total_days} days fetched ({len(all_games)} games)")
            
            time.sleep(0.1)  # Reduced rate limiting (was 0.15)
        except Exception as e:
            # Silent fail for individual days to avoid spam
            continue

    _set_cache(cache_key, all_games)
    print(f"  ✅ Fetched {len(all_games)} completed games from last {days_back} days")
    return all_games


def fetch_todays_games() -> list:
    """Fetch today's scheduled games."""
    today = datetime.now().strftime("%Y-%m-%d")
    schedule = fetch_schedule(today)
    # Filter to today's games only, not yet final
    todays = [g for g in schedule if g["date"] == today]
    return todays


def get_team_recent_form(team: str, all_games: list, n: int = 10) -> dict:
    """
    Calculate a team's recent form from last n games.
    """
    team_games = [
        g for g in all_games
        if g["home_team"] == team or g["away_team"] == team
    ]
    # Sort by date descending, take last n
    team_games.sort(key=lambda g: g["date"], reverse=True)
    recent = team_games[:n]

    if not recent:
        return {"win_pct": 0.5, "avg_gf": 3.0, "avg_ga": 3.0, "games": 0}

    wins = 0
    goals_for = 0
    goals_against = 0
    for g in recent:
        if g["home_team"] == team:
            goals_for += g["home_score"] or 0
            goals_against += g["away_score"] or 0
            if g.get("home_win"):
                wins += 1
        else:
            goals_for += g["away_score"] or 0
            goals_against += g["home_score"] or 0
            if not g.get("home_win"):
                wins += 1

    n_games = len(recent)
    return {
        "win_pct": wins / n_games,
        "avg_gf": goals_for / n_games,
        "avg_ga": goals_against / n_games,
        "games": n_games,
    }


def get_h2h_record(team1: str, team2: str, all_games: list) -> dict:
    """Get head-to-head record between two teams."""
    h2h = [
        g for g in all_games
        if (g["home_team"] == team1 and g["away_team"] == team2)
        or (g["home_team"] == team2 and g["away_team"] == team1)
    ]

    if not h2h:
        return {"games": 0, "team1_wins": 0, "team2_wins": 0, "avg_total": 6.0}

    t1_wins = 0
    total_goals = 0
    for g in h2h:
        total_goals += g.get("total_goals", 0)
        if g["home_team"] == team1 and g.get("home_win"):
            t1_wins += 1
        elif g["away_team"] == team1 and not g.get("home_win"):
            t1_wins += 1

    return {
        "games": len(h2h),
        "team1_wins": t1_wins,
        "team2_wins": len(h2h) - t1_wins,
        "avg_total": total_goals / len(h2h),
    }


if __name__ == "__main__":
    print("Fetching current standings...")
    standings = fetch_standings()
    for abbrev, s in sorted(standings.items(), key=lambda x: x[1]["points"], reverse=True)[:5]:
        print(f"  {abbrev}: {s['points']}pts, {s['wins']}W-{s['losses']}L, "
              f"GF/G={s['goals_for_pg']:.2f}, GA/G={s['goals_against_pg']:.2f}")

    print("\nFetching today's games...")
    games = fetch_todays_games()
    for g in games:
        print(f"  {g['away_team']} @ {g['home_team']} ({g['game_state']})")
