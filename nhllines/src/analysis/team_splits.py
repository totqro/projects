"""
Team Home/Road Splits Tracker
==============================
Tracks team performance splits for home vs road games.
Provides recent form (last 10 games) for both home and road.

Usage:
    from team_splits import get_team_splits, get_home_road_advantage
    
    splits = get_team_splits("TOR", all_games)
    advantage = get_home_road_advantage("TOR", "BOS", all_games)
"""

from datetime import datetime
from typing import List, Dict


def get_team_splits(team: str, all_games: List[dict], n_recent: int = 10) -> dict:
    """
    Calculate home/road splits for a team.
    
    Returns dict with:
    - home_recent: Stats from last n home games
    - road_recent: Stats from last n road games
    - home_season: Season-long home stats
    - road_season: Season-long road stats
    """
    # Separate home and road games
    home_games = [
        g for g in all_games
        if g.get("home_team") == team and g.get("game_state") in ("OFF", "FINAL")
    ]
    
    road_games = [
        g for g in all_games
        if g.get("away_team") == team and g.get("game_state") in ("OFF", "FINAL")
    ]
    
    # Sort by date descending
    home_games.sort(key=lambda g: g.get("date", ""), reverse=True)
    road_games.sort(key=lambda g: g.get("date", ""), reverse=True)
    
    # Calculate stats for recent home games
    home_recent = _calculate_split_stats(home_games[:n_recent], team, is_home=True)
    
    # Calculate stats for recent road games
    road_recent = _calculate_split_stats(road_games[:n_recent], team, is_home=False)
    
    # Calculate season-long stats
    home_season = _calculate_split_stats(home_games, team, is_home=True)
    road_season = _calculate_split_stats(road_games, team, is_home=False)
    
    return {
        "home_recent": home_recent,
        "road_recent": road_recent,
        "home_season": home_season,
        "road_season": road_season,
        "home_advantage": home_recent["win_pct"] - road_recent["win_pct"],
        "recent_games_sample": {
            "home": home_recent["games"],
            "road": road_recent["games"]
        }
    }


def _calculate_split_stats(games: List[dict], team: str, is_home: bool) -> dict:
    """
    Calculate stats for a set of games.
    
    Returns:
    - games: Number of games
    - wins: Number of wins
    - losses: Number of losses
    - ot_losses: Number of OT losses
    - win_pct: Win percentage
    - goals_for: Total goals scored
    - goals_against: Total goals allowed
    - gf_pg: Goals for per game
    - ga_pg: Goals against per game
    - goal_diff: Goal differential
    """
    if not games:
        return {
            "games": 0,
            "wins": 0,
            "losses": 0,
            "ot_losses": 0,
            "win_pct": 0.500,
            "goals_for": 0,
            "goals_against": 0,
            "gf_pg": 3.0,
            "ga_pg": 3.0,
            "goal_diff": 0.0
        }
    
    wins = 0
    losses = 0
    ot_losses = 0
    goals_for = 0
    goals_against = 0
    
    for game in games:
        if is_home:
            gf = game.get("home_score", 0)
            ga = game.get("away_score", 0)
            won = game.get("home_win", False)
        else:
            gf = game.get("away_score", 0)
            ga = game.get("home_score", 0)
            won = not game.get("home_win", True)
        
        goals_for += gf
        goals_against += ga
        
        if won:
            wins += 1
        else:
            # Check if OT loss (1-goal loss with total > regulation)
            if abs(gf - ga) == 1 and (gf + ga) > 5:  # Heuristic for OT
                ot_losses += 1
            else:
                losses += 1
    
    n_games = len(games)
    
    return {
        "games": n_games,
        "wins": wins,
        "losses": losses,
        "ot_losses": ot_losses,
        "win_pct": wins / n_games if n_games > 0 else 0.500,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "gf_pg": goals_for / n_games if n_games > 0 else 3.0,
        "ga_pg": goals_against / n_games if n_games > 0 else 3.0,
        "goal_diff": (goals_for - goals_against) / n_games if n_games > 0 else 0.0
    }


def get_home_road_advantage(home_team: str, away_team: str, all_games: List[dict], n_recent: int = 10) -> dict:
    """
    Calculate home/road advantage for a specific matchup.
    
    Returns dict with:
    - home_team_home_stats: Home team's recent home performance
    - away_team_road_stats: Away team's recent road performance
    - advantage_score: Net advantage (-100 to +100, positive = home advantage)
    - confidence: Confidence in the advantage (0-1)
    """
    home_splits = get_team_splits(home_team, all_games, n_recent)
    away_splits = get_team_splits(away_team, all_games, n_recent)
    
    home_home_stats = home_splits["home_recent"]
    away_road_stats = away_splits["road_recent"]
    
    # Calculate advantage components
    # 1. Win percentage differential (40% weight)
    win_pct_diff = (home_home_stats["win_pct"] - away_road_stats["win_pct"]) * 40
    
    # 2. Goal differential (30% weight)
    home_gd = home_home_stats["goal_diff"]
    away_gd = away_road_stats["goal_diff"]
    goal_diff_advantage = (home_gd - away_gd) * 10  # Scale to similar range
    
    # 3. Defensive performance (30% weight)
    # Lower GA/PG is better
    defensive_diff = (away_road_stats["ga_pg"] - home_home_stats["ga_pg"]) * 10
    
    # Total advantage score
    advantage_score = win_pct_diff + goal_diff_advantage + defensive_diff
    
    # Confidence based on sample size
    min_games = min(home_home_stats["games"], away_road_stats["games"])
    if min_games >= n_recent:
        confidence = 1.0
    elif min_games >= n_recent * 0.7:
        confidence = 0.8
    elif min_games >= n_recent * 0.5:
        confidence = 0.6
    else:
        confidence = 0.4
    
    return {
        "home_team": home_team,
        "away_team": away_team,
        "home_team_home_stats": home_home_stats,
        "away_team_road_stats": away_road_stats,
        "advantage_score": round(advantage_score, 1),
        "confidence": confidence,
        "interpretation": _interpret_advantage(advantage_score)
    }


def _interpret_advantage(score: float) -> str:
    """Interpret the advantage score."""
    if score > 20:
        return "Strong home advantage"
    elif score > 10:
        return "Moderate home advantage"
    elif score > -10:
        return "Even matchup"
    elif score > -20:
        return "Moderate road advantage"
    else:
        return "Strong road advantage"


def format_splits_report(team: str, splits: dict) -> str:
    """Format a readable report of team splits."""
    lines = []
    lines.append(f"\n{team} Home/Road Splits")
    lines.append("=" * 60)
    
    # Recent home
    hr = splits["home_recent"]
    lines.append(f"\nHome (Last {hr['games']} games):")
    lines.append(f"  Record: {hr['wins']}-{hr['losses']}-{hr['ot_losses']} ({hr['win_pct']:.1%})")
    lines.append(f"  Scoring: {hr['gf_pg']:.2f} GF/G, {hr['ga_pg']:.2f} GA/G")
    lines.append(f"  Goal Diff: {hr['goal_diff']:+.2f} per game")
    
    # Recent road
    rr = splits["road_recent"]
    lines.append(f"\nRoad (Last {rr['games']} games):")
    lines.append(f"  Record: {rr['wins']}-{rr['losses']}-{rr['ot_losses']} ({rr['win_pct']:.1%})")
    lines.append(f"  Scoring: {rr['gf_pg']:.2f} GF/G, {rr['ga_pg']:.2f} GA/G")
    lines.append(f"  Goal Diff: {rr['goal_diff']:+.2f} per game")
    
    # Home advantage
    lines.append(f"\nHome Advantage: {splits['home_advantage']:+.1%}")
    
    return "\n".join(lines)


if __name__ == "__main__":
    # Test with sample data
    from src.data.nhl_data import fetch_season_games
    
    print("Fetching game data...")
    all_games = fetch_season_games(days_back=90)
    
    print("\nTesting team splits...")
    test_teams = ["TOR", "BOS", "COL", "ANA"]
    
    for team in test_teams:
        splits = get_team_splits(team, all_games, n_recent=10)
        print(format_splits_report(team, splits))
    
    print("\n" + "=" * 60)
    print("Testing matchup advantage...")
    print("=" * 60)
    
    advantage = get_home_road_advantage("TOR", "BOS", all_games)
    print(f"\n{advantage['away_team']} @ {advantage['home_team']}")
    print(f"\nHome Team ({advantage['home_team']}) at Home:")
    h = advantage['home_team_home_stats']
    print(f"  {h['wins']}-{h['losses']}-{h['ot_losses']} ({h['win_pct']:.1%})")
    print(f"  {h['gf_pg']:.2f} GF/G, {h['ga_pg']:.2f} GA/G")
    
    print(f"\nAway Team ({advantage['away_team']}) on Road:")
    a = advantage['away_team_road_stats']
    print(f"  {a['wins']}-{a['losses']}-{a['ot_losses']} ({a['win_pct']:.1%})")
    print(f"  {a['gf_pg']:.2f} GF/G, {a['ga_pg']:.2f} GA/G")
    
    print(f"\nAdvantage Score: {advantage['advantage_score']:+.1f}")
    print(f"Interpretation: {advantage['interpretation']}")
    print(f"Confidence: {advantage['confidence']:.0%}")
