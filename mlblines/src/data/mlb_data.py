"""
MLB Data Fetcher
Fetches team standings, game results, pitcher stats, bullpen quality,
park factors, and L/R splits from the free MLB StatsAPI.

API docs: https://statsapi.mlb.com
No API key required.
"""

import requests
import json
import time
from pathlib import Path
from datetime import datetime, timedelta

STATS_API = "https://statsapi.mlb.com/api/v1"
CACHE_DIR = Path(__file__).parent.parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

# MLB team abbreviation map
TEAM_ABBREV_MAP = {
    108: "LAA", 109: "ARI", 110: "BAL", 111: "BOS", 112: "CHC",
    113: "CIN", 114: "CLE", 115: "COL", 116: "DET", 117: "HOU",
    118: "KC",  119: "LAD", 120: "WSH", 121: "NYM", 133: "OAK",
    134: "PIT", 135: "SD",  136: "SEA", 137: "SF",  138: "STL",
    139: "TB",  140: "TEX", 141: "TOR", 142: "MIN", 143: "PHI",
    144: "ATL", 145: "CWS", 146: "MIA", 147: "NYY", 158: "MIL",
}

TEAM_ID_BY_ABBREV = {v: k for k, v in TEAM_ABBREV_MAP.items()}

# Full name -> abbreviation (used by odds fetcher)
TEAM_FULL_TO_ABBREV = {
    "Arizona Diamondbacks": "ARI", "Atlanta Braves": "ATL",
    "Baltimore Orioles": "BAL", "Boston Red Sox": "BOS",
    "Chicago Cubs": "CHC", "Chicago White Sox": "CWS",
    "Cincinnati Reds": "CIN", "Cleveland Guardians": "CLE",
    "Colorado Rockies": "COL", "Detroit Tigers": "DET",
    "Houston Astros": "HOU", "Kansas City Royals": "KC",
    "Los Angeles Angels": "LAA", "Los Angeles Dodgers": "LAD",
    "Miami Marlins": "MIA", "Milwaukee Brewers": "MIL",
    "Minnesota Twins": "MIN", "New York Mets": "NYM",
    "New York Yankees": "NYY", "Oakland Athletics": "OAK",
    "Philadelphia Phillies": "PHI", "Pittsburgh Pirates": "PIT",
    "San Diego Padres": "SD", "San Francisco Giants": "SF",
    "Seattle Mariners": "SEA", "St. Louis Cardinals": "STL",
    "Tampa Bay Rays": "TB", "Texas Rangers": "TEX",
    "Toronto Blue Jays": "TOR", "Washington Nationals": "WSH",
}

# Park factors (runs, higher = more runs). Based on multi-year averages.
# 100 = neutral, >100 = hitter-friendly, <100 = pitcher-friendly
PARK_FACTORS = {
    "COL": 115, "CIN": 106, "TEX": 105, "ARI": 104, "BOS": 104,
    "CHC": 103, "PHI": 103, "MIL": 102, "ATL": 102, "BAL": 101,
    "CLE": 101, "MIN": 101, "CWS": 100, "NYY": 100, "DET": 100,
    "HOU": 100, "KC":  100, "LAA": 100, "STL": 100, "WSH": 100,
    "PIT": 99,  "TOR": 99,  "NYM": 98,  "SF":  98,  "SD":  97,
    "SEA": 97,  "LAD": 97,  "TB":  97,  "MIA": 96,  "OAK": 96,
}


def _cached_get(url, cache_name, ttl_seconds=3600, params=None):
    """Fetch URL with file-based caching."""
    cache_file = CACHE_DIR / f"{cache_name}.json"
    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < ttl_seconds:
            return json.loads(cache_file.read_text())

    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    cache_file.write_text(json.dumps(data, default=str))
    return data


def fetch_standings():
    """
    Fetch current MLB standings.
    Returns dict: {team_abbrev: {win_pct, wins, losses, runs_scored_pg, runs_allowed_pg, ...}}
    """
    today = datetime.now().strftime("%Y-%m-%d")
    cache_name = f"mlb_standings_{today}"
    data = _cached_get(
        f"{STATS_API}/standings",
        cache_name,
        ttl_seconds=21600,  # 6 hours
        params={"leagueId": "103,104", "season": datetime.now().year,
                "standingsTypes": "regularSeason", "hydrate": "team"},
    )

    standings = {}
    for record in data.get("records", []):
        for tr in record.get("teamRecords", []):
            team = tr.get("team", {})
            team_id = team.get("id")
            abbrev = TEAM_ABBREV_MAP.get(team_id, str(team_id))

            wins = tr.get("wins", 0)
            losses = tr.get("losses", 0)
            gp = wins + losses

            # Run differential
            rs = tr.get("runsScored", 0)
            ra = tr.get("runsAllowed", 0)

            standings[abbrev] = {
                "team_id": team_id,
                "team_name": team.get("name", abbrev),
                "wins": wins,
                "losses": losses,
                "games_played": gp,
                "win_pct": wins / max(gp, 1),
                "runs_scored": rs,
                "runs_allowed": ra,
                "runs_scored_pg": rs / max(gp, 1),
                "runs_allowed_pg": ra / max(gp, 1),
                "run_diff": rs - ra,
                "run_diff_pg": (rs - ra) / max(gp, 1),
                "home_wins": tr.get("records", {}).get("splitRecords", [{}])[0].get("wins", 0) if tr.get("records", {}).get("splitRecords") else 0,
                "home_losses": tr.get("records", {}).get("splitRecords", [{}])[0].get("losses", 0) if tr.get("records", {}).get("splitRecords") else 0,
                "away_wins": tr.get("records", {}).get("splitRecords", [{}])[1].get("wins", 0) if tr.get("records", {}).get("splitRecords") and len(tr["records"]["splitRecords"]) > 1 else 0,
                "away_losses": tr.get("records", {}).get("splitRecords", [{}])[1].get("losses", 0) if tr.get("records", {}).get("splitRecords") and len(tr["records"]["splitRecords"]) > 1 else 0,
                "park_factor": PARK_FACTORS.get(abbrev, 100),
            }

    return standings


def fetch_season_games(days_back=90):
    """
    Fetch completed MLB games from the last N days.
    Returns list of game dicts with scores, pitchers, etc.
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)

    all_games = []
    # Fetch in weekly chunks to avoid huge responses
    current = start_date
    while current < end_date:
        chunk_end = min(current + timedelta(days=7), end_date)
        start_str = current.strftime("%Y-%m-%d")
        end_str = chunk_end.strftime("%Y-%m-%d")
        cache_name = f"mlb_games_{start_str}_{end_str}"

        data = _cached_get(
            f"{STATS_API}/schedule",
            cache_name,
            ttl_seconds=43200,  # 12 hours
            params={
                "sportId": 1,
                "startDate": start_str,
                "endDate": end_str,
                "gameType": "R,S",  # Regular season + spring training
                "hydrate": "probablePitcher,linescore,decisions",
            },
        )

        for date_entry in data.get("dates", []):
            for game in date_entry.get("games", []):
                status = game.get("status", {}).get("abstractGameState", "")
                if status != "Final":
                    continue

                teams = game.get("teams", {})
                home = teams.get("home", {})
                away = teams.get("away", {})
                home_team_id = home.get("team", {}).get("id")
                away_team_id = away.get("team", {}).get("id")

                home_abbrev = TEAM_ABBREV_MAP.get(home_team_id, str(home_team_id))
                away_abbrev = TEAM_ABBREV_MAP.get(away_team_id, str(away_team_id))

                home_score = home.get("score", 0)
                away_score = away.get("score", 0)

                # Probable pitchers
                home_pitcher = home.get("probablePitcher", {})
                away_pitcher = away.get("probablePitcher", {})

                linescore = game.get("linescore", {})
                innings = len(linescore.get("innings", []))

                all_games.append({
                    "game_id": game.get("gamePk"),
                    "date": game.get("officialDate", date_entry.get("date", "")),
                    "home_team": home_abbrev,
                    "away_team": away_abbrev,
                    "home_score": home_score,
                    "away_score": away_score,
                    "total_runs": home_score + away_score,
                    "home_win": home_score > away_score,
                    "run_diff": home_score - away_score,
                    "innings": innings,
                    "home_pitcher_id": home_pitcher.get("id"),
                    "home_pitcher_name": home_pitcher.get("fullName", "Unknown"),
                    "away_pitcher_id": away_pitcher.get("id"),
                    "away_pitcher_name": away_pitcher.get("fullName", "Unknown"),
                    "game_state": "FINAL",
                })

        current = chunk_end

    return all_games


def fetch_todays_games():
    """Fetch today's scheduled MLB games."""
    today = datetime.now().strftime("%Y-%m-%d")
    cache_name = f"mlb_today_{today}_{datetime.now().hour}"

    data = _cached_get(
        f"{STATS_API}/schedule",
        cache_name,
        ttl_seconds=1800,
        params={
            "sportId": 1,
            "date": today,
            "gameType": "R,S",
            "hydrate": "probablePitcher,linescore",
        },
    )

    games = []
    for date_entry in data.get("dates", []):
        for game in date_entry.get("games", []):
            status = game.get("status", {}).get("abstractGameState", "")
            if status == "Final":
                continue  # Skip finished games

            teams = game.get("teams", {})
            home = teams.get("home", {})
            away = teams.get("away", {})
            home_id = home.get("team", {}).get("id")
            away_id = away.get("team", {}).get("id")

            home_pitcher = home.get("probablePitcher", {})
            away_pitcher = away.get("probablePitcher", {})

            games.append({
                "game_id": game.get("gamePk"),
                "game_datetime": game.get("gameDate", ""),
                "home_team": TEAM_ABBREV_MAP.get(home_id, str(home_id)),
                "away_team": TEAM_ABBREV_MAP.get(away_id, str(away_id)),
                "home_pitcher_id": home_pitcher.get("id"),
                "home_pitcher_name": home_pitcher.get("fullName", "TBD"),
                "away_pitcher_id": away_pitcher.get("id"),
                "away_pitcher_name": away_pitcher.get("fullName", "TBD"),
            })

    return games


def get_pitcher_stats(pitcher_id, season=None):
    """
    Fetch season stats for a pitcher.
    Returns dict with ERA, WHIP, K/9, BB/9, HR/9, FIP, etc.
    """
    if not pitcher_id:
        return _default_pitcher_stats()

    if season is None:
        season = datetime.now().year

    cache_name = f"mlb_pitcher_{pitcher_id}_{season}"
    try:
        data = _cached_get(
            f"{STATS_API}/people/{pitcher_id}",
            cache_name,
            ttl_seconds=21600,
            params={
                "hydrate": f"stats(group=[pitching],type=[season],season={season}),currentTeam",
            },
        )
    except Exception:
        return _default_pitcher_stats()

    people = data.get("people", [])
    if not people:
        return _default_pitcher_stats()

    person = people[0]
    stats_groups = person.get("stats", [])

    for sg in stats_groups:
        if sg.get("group", {}).get("displayName") == "pitching":
            splits = sg.get("splits", [])
            if not splits:
                continue
            s = splits[0].get("stat", {})

            ip_str = str(s.get("inningsPitched", "0"))
            ip = _parse_innings(ip_str)

            era = float(s.get("era", "4.50"))
            whip = float(s.get("whip", "1.30"))
            k9 = float(s.get("strikeoutsPer9Inn", "8.0")) if s.get("strikeoutsPer9Inn") else 8.0
            bb9 = float(s.get("walksPer9Inn", "3.0")) if s.get("walksPer9Inn") else 3.0
            hr9 = float(s.get("homeRunsPer9", "1.2")) if s.get("homeRunsPer9") else 1.2
            wins = int(s.get("wins", 0))
            losses = int(s.get("losses", 0))
            games_started = int(s.get("gamesStarted", 0))
            avg_against = float(s.get("avg", ".250")) if s.get("avg") else 0.250

            # Calculate FIP approximation: (13*HR + 3*BB - 2*K) / IP + 3.10
            hr = int(s.get("homeRuns", 0))
            bb = int(s.get("baseOnBalls", 0))
            k = int(s.get("strikeOuts", 0))
            fip = ((13 * hr + 3 * bb - 2 * k) / max(ip, 1)) + 3.10 if ip > 0 else era

            return {
                "pitcher_id": pitcher_id,
                "name": person.get("fullName", "Unknown"),
                "era": era,
                "whip": whip,
                "k_per_9": k9,
                "bb_per_9": bb9,
                "hr_per_9": hr9,
                "fip": round(fip, 2),
                "innings_pitched": ip,
                "games_started": games_started,
                "wins": wins,
                "losses": losses,
                "avg_against": avg_against,
                "quality_score": _pitcher_quality_score(era, whip, k9, bb9, ip, games_started),
                "handedness": person.get("pitchHand", {}).get("code", "R"),
            }

    return _default_pitcher_stats()


def _default_pitcher_stats():
    """Return league-average pitcher stats as defaults."""
    return {
        "pitcher_id": None,
        "name": "Unknown",
        "era": 4.50,
        "whip": 1.30,
        "k_per_9": 8.0,
        "bb_per_9": 3.2,
        "hr_per_9": 1.2,
        "fip": 4.30,
        "innings_pitched": 0,
        "games_started": 0,
        "wins": 0,
        "losses": 0,
        "avg_against": 0.250,
        "quality_score": 50,
        "handedness": "R",
    }


def _pitcher_quality_score(era, whip, k9, bb9, ip, gs):
    """
    Compute a 0-100 quality score for a pitcher.
    50 = league average, 80+ = ace, 30- = below replacement.
    """
    # ERA component (40%): 4.50 = avg (50), 2.0 = elite (100), 7.0 = terrible (0)
    era_score = max(0, min(100, 100 - (era - 2.0) * 20))

    # WHIP component (25%): 1.30 = avg (50), 0.90 = elite (100), 1.70 = bad (0)
    whip_score = max(0, min(100, 100 - (whip - 0.90) * 62.5))

    # K/9 component (20%): 8.0 = avg (50), 12.0 = elite (100), 4.0 = bad (0)
    k_score = max(0, min(100, (k9 - 4.0) * 12.5))

    # BB/9 component (10%): 3.2 = avg (50), 1.5 = elite (100), 5.0 = bad (0)
    bb_score = max(0, min(100, 100 - (bb9 - 1.5) * 28.6))

    # Experience bonus (5%): more starts = more reliable
    exp_score = min(100, gs * 4)

    score = (era_score * 0.40 + whip_score * 0.25 + k_score * 0.20 +
             bb_score * 0.10 + exp_score * 0.05)

    return round(max(0, min(100, score)), 1)


def _parse_innings(ip_str):
    """Parse innings pitched string like '156.2' -> 156.67."""
    try:
        parts = str(ip_str).split(".")
        full = int(parts[0])
        thirds = int(parts[1]) if len(parts) > 1 else 0
        return full + thirds / 3.0
    except (ValueError, IndexError):
        return 0.0


def get_bullpen_stats(team_abbrev, all_games=None):
    """
    Calculate team bullpen quality from recent games.
    Returns dict with bullpen ERA estimate, usage, etc.
    """
    team_id = TEAM_ID_BY_ABBREV.get(team_abbrev)
    if not team_id:
        return {"bullpen_era": 4.00, "bullpen_quality": 50}

    season = datetime.now().year
    cache_name = f"mlb_team_pitching_{team_abbrev}_{season}"

    try:
        data = _cached_get(
            f"{STATS_API}/teams/{team_id}/stats",
            cache_name,
            ttl_seconds=21600,
            params={
                "stats": "season",
                "group": "pitching",
                "season": season,
            },
        )

        for sg in data.get("stats", []):
            splits = sg.get("splits", [])
            if splits:
                s = splits[0].get("stat", {})
                team_era = float(s.get("era", "4.00"))
                team_whip = float(s.get("whip", "1.30"))
                team_k9 = float(s.get("strikeoutsPer9Inn", "8.0")) if s.get("strikeoutsPer9Inn") else 8.0

                # Bullpen ERA is typically close to team ERA
                # We'll estimate it as team_era * 1.05 (relievers slightly worse on avg)
                bullpen_era = team_era * 1.05

                quality = _pitcher_quality_score(bullpen_era, team_whip, team_k9, 3.2, 500, 30)

                return {
                    "bullpen_era": round(bullpen_era, 2),
                    "bullpen_whip": round(team_whip * 1.03, 2),
                    "bullpen_k9": round(team_k9 * 0.95, 1),
                    "bullpen_quality": round(quality, 1),
                    "team_era": team_era,
                }
    except Exception:
        pass

    return {"bullpen_era": 4.00, "bullpen_whip": 1.30, "bullpen_k9": 8.0, "bullpen_quality": 50, "team_era": 4.00}


def get_team_recent_form(team_abbrev, all_games, n=10):
    """
    Get a team's recent form (last N games).
    Returns dict with win_pct, avg_rs, avg_ra.
    """
    team_games = [
        g for g in all_games
        if (g["home_team"] == team_abbrev or g["away_team"] == team_abbrev)
        and g.get("game_state") == "FINAL"
    ]
    team_games.sort(key=lambda g: g["date"], reverse=True)
    recent = team_games[:n]

    if not recent:
        return {"win_pct": 0.5, "avg_rs": 4.5, "avg_ra": 4.5, "games": 0}

    wins = 0
    total_rs = 0
    total_ra = 0

    for g in recent:
        if g["home_team"] == team_abbrev:
            total_rs += g["home_score"]
            total_ra += g["away_score"]
            if g["home_win"]:
                wins += 1
        else:
            total_rs += g["away_score"]
            total_ra += g["home_score"]
            if not g["home_win"]:
                wins += 1

    ng = len(recent)
    return {
        "win_pct": wins / ng,
        "avg_rs": total_rs / ng,
        "avg_ra": total_ra / ng,
        "games": ng,
    }


def get_h2h_record(home_team, away_team, all_games, n=20):
    """Get head-to-head record between two teams from recent games."""
    h2h = [
        g for g in all_games
        if ((g["home_team"] == home_team and g["away_team"] == away_team) or
            (g["home_team"] == away_team and g["away_team"] == home_team))
        and g.get("game_state") == "FINAL"
    ]
    h2h.sort(key=lambda g: g["date"], reverse=True)
    h2h = h2h[:n]

    if not h2h:
        return {"games": 0, "home_wins": 0, "away_wins": 0, "avg_total": 9.0}

    home_wins = 0
    total_runs = 0
    for g in h2h:
        total_runs += g["total_runs"]
        if g["home_team"] == home_team and g["home_win"]:
            home_wins += 1
        elif g["away_team"] == home_team and not g["home_win"]:
            home_wins += 1

    return {
        "games": len(h2h),
        "home_wins": home_wins,
        "away_wins": len(h2h) - home_wins,
        "avg_total": total_runs / len(h2h),
    }


def get_park_factors(team_abbrev):
    """Get park factor for a team's home ballpark."""
    return PARK_FACTORS.get(team_abbrev, 100)


def get_team_splits(team_abbrev, all_games, n_recent=10):
    """
    Calculate home/road splits for a team.
    Returns dict with home_recent and road_recent performance.
    """
    home_games = [
        g for g in all_games
        if g["home_team"] == team_abbrev and g.get("game_state") == "FINAL"
    ]
    road_games = [
        g for g in all_games
        if g["away_team"] == team_abbrev and g.get("game_state") == "FINAL"
    ]

    home_games.sort(key=lambda g: g["date"], reverse=True)
    road_games.sort(key=lambda g: g["date"], reverse=True)

    def _calc_split(games, is_home):
        if not games:
            return {"win_pct": 0.5, "rs_pg": 4.5, "ra_pg": 4.5, "run_diff": 0.0, "games": 0}
        wins = 0
        rs_total = 0
        ra_total = 0
        for g in games:
            if is_home:
                rs_total += g["home_score"]
                ra_total += g["away_score"]
                if g["home_win"]:
                    wins += 1
            else:
                rs_total += g["away_score"]
                ra_total += g["home_score"]
                if not g["home_win"]:
                    wins += 1
        ng = len(games)
        return {
            "win_pct": wins / ng,
            "rs_pg": round(rs_total / ng, 2),
            "ra_pg": round(ra_total / ng, 2),
            "run_diff": round((rs_total - ra_total) / ng, 2),
            "games": ng,
        }

    return {
        "home_recent": _calc_split(home_games[:n_recent], is_home=True),
        "road_recent": _calc_split(road_games[:n_recent], is_home=False),
        "home_season": _calc_split(home_games, is_home=True),
        "road_season": _calc_split(road_games, is_home=False),
    }


def get_team_batting_splits(team_abbrev):
    """
    Fetch team batting stats vs LHP and RHP.
    Returns L/R split data for context features.
    """
    team_id = TEAM_ID_BY_ABBREV.get(team_abbrev)
    if not team_id:
        return {"vs_lhp": {"avg": 0.250, "ops": 0.720}, "vs_rhp": {"avg": 0.255, "ops": 0.730}}

    season = datetime.now().year
    cache_name = f"mlb_batting_splits_{team_abbrev}_{season}"

    try:
        data = _cached_get(
            f"{STATS_API}/teams/{team_id}/stats",
            cache_name,
            ttl_seconds=43200,
            params={
                "stats": "vsPitchType",  # This gives splits
                "group": "hitting",
                "season": season,
            },
        )

        # Fallback: use season averages and approximate L/R splits
        for sg in data.get("stats", []):
            splits = sg.get("splits", [])
            if splits:
                s = splits[0].get("stat", {})
                avg = float(s.get("avg", ".250")) if s.get("avg") else 0.250
                ops = float(s.get("ops", ".720")) if s.get("ops") else 0.720
                return {
                    "vs_lhp": {"avg": round(avg - 0.005, 3), "ops": round(ops - 0.015, 3)},
                    "vs_rhp": {"avg": round(avg + 0.005, 3), "ops": round(ops + 0.015, 3)},
                }
    except Exception:
        pass

    return {"vs_lhp": {"avg": 0.250, "ops": 0.720}, "vs_rhp": {"avg": 0.255, "ops": 0.730}}


def get_rest_days(team_abbrev, game_date, all_games):
    """Calculate rest days for a team before a given game date."""
    team_games = [
        g for g in all_games
        if (g["home_team"] == team_abbrev or g["away_team"] == team_abbrev)
        and g.get("game_state") == "FINAL"
        and g["date"] < game_date
    ]
    if not team_games:
        return 2  # Default

    team_games.sort(key=lambda g: g["date"], reverse=True)
    last_game_date = team_games[0]["date"]

    try:
        gd = datetime.strptime(game_date, "%Y-%m-%d")
        lgd = datetime.strptime(last_game_date, "%Y-%m-%d")
        return (gd - lgd).days
    except ValueError:
        return 2


if __name__ == "__main__":
    print("Fetching MLB standings...")
    standings = fetch_standings()
    print(f"Loaded {len(standings)} teams")
    for team, stats in sorted(standings.items(), key=lambda x: x[1]["win_pct"], reverse=True)[:5]:
        print(f"  {team}: {stats['wins']}-{stats['losses']} ({stats['win_pct']:.3f}) "
              f"RS/G: {stats['runs_scored_pg']:.1f} RA/G: {stats['runs_allowed_pg']:.1f}")
