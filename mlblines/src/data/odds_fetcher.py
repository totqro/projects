"""
MLB Odds Fetcher
Fetches live MLB betting lines from The Odds API.
Supports moneyline (h2h), run lines (spreads), and totals (over/under).
Multi-key rotation for quota management.
"""

import requests
import json
import os
import time
from pathlib import Path
from datetime import datetime

ODDS_API_BASE = "https://api.the-odds-api.com/v4"
CACHE_DIR = Path(__file__).parent.parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

PREFERRED_BOOKS = [
    "draftkings", "fanduel", "betmgm", "betrivers",
    "pointsbet", "bet365", "pinnacle", "bovada",
]

MARKETS = "h2h,spreads,totals"

# Full name -> abbreviation mapping for The Odds API
TEAM_NAME_TO_ABBREV = {
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


def team_name_to_abbrev(name: str) -> str:
    """Convert full team name to MLB abbreviation."""
    return TEAM_NAME_TO_ABBREV.get(name, name)


def get_api_keys() -> list:
    """Get all available Odds API keys from environment or config."""
    keys = []
    env_key = os.environ.get("ODDS_API_KEY", "")
    if env_key:
        keys.append(env_key)

    config_path = Path(__file__).parent.parent.parent / "config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
        primary = config.get("odds_api_key", "")
        if primary and primary not in keys:
            keys.append(primary)
        for i in range(2, 10):
            key_name = f"odds_api_key_{['two','three','four','five','six','seven','eight','nine'][i-2]}"
            key = config.get(key_name, "")
            if key and key not in keys:
                keys.append(key)

    if not keys:
        raise ValueError(
            "No API key found!\n"
            "1. Sign up free at https://the-odds-api.com\n"
            "2. Set ODDS_API_KEY env var, or create config.json"
        )
    return keys


def get_api_key_with_quota() -> tuple:
    """Get an API key with remaining quota. Returns (key, index)."""
    keys = get_api_keys()
    quota_cache = CACHE_DIR / "quota_info.json"
    quota_info = {}
    if quota_cache.exists():
        try:
            quota_info = json.loads(quota_cache.read_text())
        except Exception:
            quota_info = {}

    for i, key in enumerate(keys):
        key_quota = quota_info.get(f"key_{i}", {})
        remaining = key_quota.get("requests_remaining", 500)
        if remaining > 10:
            return key, i

    print("  Warning: All API keys may be exhausted")
    return keys[0], 0


def update_quota_info(key_index: int, quota_data: dict):
    """Update quota info for a specific key."""
    quota_cache = CACHE_DIR / "quota_info.json"
    all_quota = {}
    if quota_cache.exists():
        try:
            all_quota = json.loads(quota_cache.read_text())
        except Exception:
            pass
    all_quota[f"key_{key_index}"] = {
        "requests_used": quota_data.get("requests_used", 0),
        "requests_remaining": quota_data.get("requests_remaining", 0),
        "last_updated": datetime.now().isoformat(),
    }
    quota_cache.write_text(json.dumps(all_quota, indent=2))


def get_quota_summary() -> dict:
    """Get quota summary across all keys."""
    keys = get_api_keys()
    quota_cache = CACHE_DIR / "quota_info.json"
    quota_info = {}
    if quota_cache.exists():
        try:
            quota_info = json.loads(quota_cache.read_text())
        except Exception:
            pass

    summary = {"total_keys": len(keys), "total_remaining": 0, "total_used": 0, "keys": []}
    for i in range(len(keys)):
        kq = quota_info.get(f"key_{i}", {})
        used = kq.get("requests_used", 0)
        remaining = kq.get("requests_remaining", 500)
        summary["total_used"] += used
        summary["total_remaining"] += remaining
        summary["keys"].append({"index": i, "used": used, "remaining": remaining})
    return summary


def american_to_decimal(american: int) -> float:
    """Convert American odds to decimal odds."""
    if american > 0:
        return 1 + (american / 100)
    else:
        return 1 + (100 / abs(american))


def american_to_implied_prob(american: int) -> float:
    """Convert American odds to implied probability."""
    if american < 0:
        return abs(american) / (abs(american) + 100)
    else:
        return 100 / (american + 100)


def fetch_mlb_odds(markets: str = MARKETS):
    """
    Fetch current MLB odds for all available games.
    Returns (games, quota_summary).
    """
    api_key, key_index = get_api_key_with_quota()
    cache_key = f"odds_mlb_{markets.replace(',','_')}_{datetime.now().strftime('%Y%m%d_%H')}"
    cached_path = CACHE_DIR / f"{cache_key}.json"

    if cached_path.exists():
        age = time.time() - cached_path.stat().st_mtime
        if age < 1800:
            return json.loads(cached_path.read_text()), get_quota_summary()

    url = f"{ODDS_API_BASE}/sports/baseball_mlb/odds"
    params = {
        "apiKey": api_key,
        "regions": "us,us2",
        "markets": markets,
        "oddsFormat": "american",
    }

    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    games = resp.json()

    remaining = resp.headers.get("x-requests-remaining", "?")
    used = resp.headers.get("x-requests-used", "?")

    update_quota_info(key_index, {
        "requests_used": int(used) if used != "?" else 0,
        "requests_remaining": int(remaining) if remaining != "?" else 0,
    })

    quota_summary = get_quota_summary()
    if quota_summary["total_keys"] > 1:
        print(f"  Odds API: Using key #{key_index + 1}/{quota_summary['total_keys']}")
        print(f"  Total quota: {quota_summary['total_used']} used, {quota_summary['total_remaining']} remaining")
    else:
        print(f"  Odds API: {used} requests used, {remaining} remaining this month")

    cached_path.write_text(json.dumps(games, default=str))
    return games, quota_summary


def parse_odds(games: list) -> list:
    """Parse raw odds API response into structured data."""
    parsed = []
    for game in games:
        game_data = {
            "game_id": game["id"],
            "commence_time": game["commence_time"],
            "home_team": game["home_team"],
            "away_team": game["away_team"],
            "bookmakers": {},
        }
        for bk in game.get("bookmakers", []):
            bk_key = bk["key"]
            bk_data = {"name": bk["title"], "markets": {}}
            for market in bk.get("markets", []):
                mk = market["key"]
                outcomes = []
                for outcome in market.get("outcomes", []):
                    o = {"name": outcome["name"], "price": outcome["price"]}
                    if "point" in outcome:
                        o["point"] = outcome["point"]
                    outcomes.append(o)
                bk_data["markets"][mk] = outcomes
            game_data["bookmakers"][bk_key] = bk_data
        parsed.append(game_data)
    return parsed


def get_best_odds(game_data: dict) -> dict:
    """Find the best available odds across bookmakers for each market."""
    best = {
        "home_team": game_data["home_team"],
        "away_team": game_data["away_team"],
        "commence_time": game_data["commence_time"],
        "moneyline": {"home": None, "away": None},
        "spread": {"home": None, "away": None},
        "total": {"over": None, "under": None},
        "all_books": {},
    }

    for bk_key, bk_data in game_data["bookmakers"].items():
        book_odds = {}

        if "h2h" in bk_data["markets"]:
            for outcome in bk_data["markets"]["h2h"]:
                side = "home" if outcome["name"] == game_data["home_team"] else "away"
                book_odds[f"ml_{side}"] = outcome["price"]
                current = best["moneyline"][side]
                if current is None or outcome["price"] > current["price"]:
                    best["moneyline"][side] = {
                        "price": outcome["price"],
                        "book": bk_key,
                        "decimal": american_to_decimal(outcome["price"]),
                        "implied_prob": american_to_implied_prob(outcome["price"]),
                    }

        if "spreads" in bk_data["markets"]:
            for outcome in bk_data["markets"]["spreads"]:
                side = "home" if outcome["name"] == game_data["home_team"] else "away"
                point = outcome.get("point", 0)
                book_odds[f"spread_{side}"] = {"price": outcome["price"], "point": point}
                current = best["spread"][side]
                if current is None or outcome["price"] > current["price"]:
                    best["spread"][side] = {
                        "price": outcome["price"],
                        "point": point,
                        "book": bk_key,
                        "decimal": american_to_decimal(outcome["price"]),
                        "implied_prob": american_to_implied_prob(outcome["price"]),
                    }

        if "totals" in bk_data["markets"]:
            for outcome in bk_data["markets"]["totals"]:
                side = "over" if outcome["name"] == "Over" else "under"
                point = outcome.get("point", 0)
                book_odds[f"total_{side}"] = {"price": outcome["price"], "point": point}
                current = best["total"][side]
                if current is None or outcome["price"] > current["price"]:
                    best["total"][side] = {
                        "price": outcome["price"],
                        "point": point,
                        "book": bk_key,
                        "decimal": american_to_decimal(outcome["price"]),
                        "implied_prob": american_to_implied_prob(outcome["price"]),
                    }

        best["all_books"][bk_key] = book_odds

    return best


def get_consensus_no_vig_odds(game_data: dict) -> dict:
    """Calculate consensus fair probabilities by averaging across books."""
    ml_home_probs = []
    ml_away_probs = []
    total_over_probs = []
    spread_home_probs = []
    total_line = None
    spread_line = None

    for bk_key, bk_data in game_data["bookmakers"].items():
        if "h2h" in bk_data["markets"]:
            probs = {}
            for outcome in bk_data["markets"]["h2h"]:
                side = "home" if outcome["name"] == game_data["home_team"] else "away"
                probs[side] = american_to_implied_prob(outcome["price"])
            total_prob = sum(probs.values())
            if total_prob > 0:
                if "home" in probs:
                    ml_home_probs.append(probs["home"] / total_prob)
                if "away" in probs:
                    ml_away_probs.append(probs["away"] / total_prob)

        if "totals" in bk_data["markets"]:
            probs = {}
            for outcome in bk_data["markets"]["totals"]:
                side = outcome["name"].lower()
                probs[side] = american_to_implied_prob(outcome["price"])
                if total_line is None and "point" in outcome:
                    total_line = outcome["point"]
            total_prob = sum(probs.values())
            if total_prob > 0 and "over" in probs:
                total_over_probs.append(probs["over"] / total_prob)

        if "spreads" in bk_data["markets"]:
            probs = {}
            for outcome in bk_data["markets"]["spreads"]:
                side = "home" if outcome["name"] == game_data["home_team"] else "away"
                probs[side] = american_to_implied_prob(outcome["price"])
                if spread_line is None and "point" in outcome and side == "home":
                    spread_line = outcome["point"]
            total_prob = sum(probs.values())
            if total_prob > 0 and "home" in probs:
                spread_home_probs.append(probs["home"] / total_prob)

    return {
        "home_win_prob": sum(ml_home_probs) / len(ml_home_probs) if ml_home_probs else 0.5,
        "away_win_prob": sum(ml_away_probs) / len(ml_away_probs) if ml_away_probs else 0.5,
        "over_prob": sum(total_over_probs) / len(total_over_probs) if total_over_probs else 0.5,
        "under_prob": 1 - (sum(total_over_probs) / len(total_over_probs)) if total_over_probs else 0.5,
        "spread_home_cover_prob": sum(spread_home_probs) / len(spread_home_probs) if spread_home_probs else 0.5,
        "total_line": total_line,
        "spread_line": spread_line,
        "n_books_ml": len(ml_home_probs),
        "n_books_total": len(total_over_probs),
    }
