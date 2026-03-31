"""
Odds Fetcher Module
Fetches live NHL betting lines from The Odds API.
Free tier: 500 requests/month — sign up at https://the-odds-api.com

Supports moneyline (h2h), spreads (puck line), and totals (over/under).
Includes theScore and other Ontario-available books.
"""

import requests
import json
import os
from pathlib import Path
from datetime import datetime
import time

ODDS_API_BASE = "https://api.the-odds-api.com/v4"
CACHE_DIR = Path(__file__).parent.parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

# Ontario/Canada-relevant bookmakers
# The Odds API 'us' region includes many books available in Ontario
PREFERRED_BOOKS = [
    "thescore",        # theScore Bet (primary)
    "fanduel",         # FanDuel (available in ON)
    "draftkings",      # DraftKings (available in ON)
    "betrivers",       # BetRivers (available in ON)
    "pointsbet",       # PointsBet (available in ON)
    "bet365",          # bet365 (available in ON)
    "betway",          # Betway
    "pinnacle",        # Pinnacle (sharp book, good for fair odds)
]

# Markets we care about
MARKETS = "h2h,spreads,totals"


def get_api_keys() -> list:
    """
    Get all available Odds API keys from environment variables or config file.
    Returns list of API keys.
    """
    keys = []
    
    # Check environment variable
    env_key = os.environ.get("ODDS_API_KEY", "")
    if env_key:
        keys.append(env_key)
    
    # Check config file for multiple keys
    config_path = Path(__file__).parent.parent.parent / "config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
        
        # Primary key
        primary_key = config.get("odds_api_key", "")
        if primary_key and primary_key not in keys:
            keys.append(primary_key)
        
        # Secondary keys (odds_api_key_two, odds_api_key_three, etc.)
        for i in range(2, 10):  # Support up to 9 keys
            key_name = f"odds_api_key_{['two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine'][i-2]}"
            key = config.get(key_name, "")
            if key and key not in keys:
                keys.append(key)
    
    if not keys:
        raise ValueError(
            "No API key found!\n"
            "1. Sign up free at https://the-odds-api.com\n"
            "2. Either set ODDS_API_KEY environment variable, or\n"
            "3. Create config.json with: {\"odds_api_key\": \"YOUR_KEY\", \"odds_api_key_two\": \"KEY2\"}"
        )
    
    return keys


def get_api_key_with_quota() -> tuple:
    """
    Get an API key that still has quota remaining.
    Returns (api_key, key_index).
    Automatically rotates to next key if current one is exhausted.
    """
    keys = get_api_keys()
    quota_cache_path = CACHE_DIR / "quota_info.json"
    
    # Load quota info for all keys
    quota_info = {}
    if quota_cache_path.exists():
        try:
            quota_info = json.loads(quota_cache_path.read_text())
        except:
            quota_info = {}
    
    # Try each key in order
    for i, key in enumerate(keys):
        key_id = f"key_{i}"
        key_quota = quota_info.get(key_id, {})
        
        requests_used = key_quota.get("requests_used", 0)
        requests_remaining = key_quota.get("requests_remaining", 500)
        
        # If this key has quota remaining, use it
        if requests_remaining > 10:  # Keep 10 request buffer
            return key, i
    
    # All keys exhausted - use first key anyway (will fail gracefully)
    print("  ⚠️  Warning: All API keys may be exhausted")
    return keys[0], 0


def update_quota_info(key_index: int, quota_data: dict):
    """
    Update quota information for a specific API key.
    """
    quota_cache_path = CACHE_DIR / "quota_info.json"
    
    # Load existing quota info
    all_quota = {}
    if quota_cache_path.exists():
        try:
            all_quota = json.loads(quota_cache_path.read_text())
        except:
            all_quota = {}
    
    # Update this key's quota
    key_id = f"key_{key_index}"
    all_quota[key_id] = {
        "requests_used": quota_data.get("requests_used", 0),
        "requests_remaining": quota_data.get("requests_remaining", 0),
        "last_updated": datetime.now().isoformat()
    }
    
    # Save
    quota_cache_path.write_text(json.dumps(all_quota, indent=2))


def get_quota_summary() -> dict:
    """
    Get summary of quota usage across all API keys.
    """
    keys = get_api_keys()
    quota_cache_path = CACHE_DIR / "quota_info.json"
    
    quota_info = {}
    if quota_cache_path.exists():
        try:
            quota_info = json.loads(quota_cache_path.read_text())
        except:
            quota_info = {}
    
    summary = {
        "total_keys": len(keys),
        "total_remaining": 0,
        "total_used": 0,
        "keys": []
    }
    
    for i in range(len(keys)):
        key_id = f"key_{i}"
        key_quota = quota_info.get(key_id, {})
        
        used = key_quota.get("requests_used", 0)
        remaining = key_quota.get("requests_remaining", 500)
        
        summary["total_used"] += used
        summary["total_remaining"] += remaining
        summary["keys"].append({
            "index": i,
            "used": used,
            "remaining": remaining,
            "last_updated": key_quota.get("last_updated", "Never")
        })
    
    return summary


def _cache_key(name: str) -> str:
    return f"odds_{name}_{datetime.now().strftime('%Y%m%d_%H')}"


def fetch_nhl_odds(markets: str = MARKETS):
    """
    Fetch current NHL odds for all available games.
    Returns tuple of (games, quota_info).
    Automatically rotates between multiple API keys.
    """
    # Get API key with available quota
    api_key, key_index = get_api_key_with_quota()

    cache_key = _cache_key(f"nhl_{markets.replace(',', '_')}")
    cached_path = CACHE_DIR / f"{cache_key}.json"
    
    if cached_path.exists():
        age = time.time() - cached_path.stat().st_mtime
        if age < 1800:  # 30 min cache for odds
            # Return cached data with quota summary
            quota_summary = get_quota_summary()
            return json.loads(cached_path.read_text()), quota_summary

    url = f"{ODDS_API_BASE}/sports/icehockey_nhl/odds"
    params = {
        "apiKey": api_key,
        "regions": "us,us2",  # covers most Ontario books
        "markets": markets,
        "oddsFormat": "american",
    }

    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    games = resp.json()

    # Log remaining requests for this key
    remaining = resp.headers.get("x-requests-remaining", "?")
    used = resp.headers.get("x-requests-used", "?")
    last_cost = resp.headers.get("x-requests-last", "?")
    
    # Update quota info for this specific key
    quota_data = {
        "requests_used": int(used) if used != "?" else 0,
        "requests_remaining": int(remaining) if remaining != "?" else 0,
    }
    update_quota_info(key_index, quota_data)
    
    # Get overall quota summary
    quota_summary = get_quota_summary()
    
    # Display quota info
    if quota_summary["total_keys"] > 1:
        print(f"  Odds API: Using key #{key_index + 1}/{quota_summary['total_keys']}")
        print(f"  Total quota: {quota_summary['total_used']} used, {quota_summary['total_remaining']} remaining across all keys")
    else:
        print(f"  Odds API: {used} requests used, {remaining} remaining this month")

    cached_path.write_text(json.dumps(games, default=str))
    
    return games, quota_summary


def parse_odds(games: list) -> list:
    """
    Parse raw odds API response into clean structured data.
    Returns list of dicts, one per game, with nested odds by bookmaker.
    """
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
                    o = {
                        "name": outcome["name"],
                        "price": outcome["price"],
                    }
                    if "point" in outcome:
                        o["point"] = outcome["point"]
                    outcomes.append(o)
                bk_data["markets"][mk] = outcomes

            game_data["bookmakers"][bk_key] = bk_data

        parsed.append(game_data)

    return parsed


def american_to_decimal(american: int) -> float:
    """Convert American odds to decimal odds."""
    if american > 0:
        return 1 + (american / 100)
    else:
        return 1 + (100 / abs(american))


def american_to_implied_prob(american: int) -> float:
    """Convert American odds to implied probability (no-vig)."""
    if american < 0:
        return abs(american) / (abs(american) + 100)
    else:
        return 100 / (american + 100)


def get_best_odds(game_data: dict, preferred_books: list = None) -> dict:
    """
    For a single game, find the best available odds across bookmakers
    for each market (moneyline, spread, total).
    Prioritizes preferred bookmakers but includes all.
    """
    if preferred_books is None:
        preferred_books = PREFERRED_BOOKS

    best = {
        "home_team": game_data["home_team"],
        "away_team": game_data["away_team"],
        "commence_time": game_data["commence_time"],
        "moneyline": {"home": None, "away": None},
        "spread": {"home": None, "away": None},
        "total": {"over": None, "under": None},
        "thescore": {"moneyline": {}, "spread": {}, "total": {}},
        "all_books": {},
    }

    for bk_key, bk_data in game_data["bookmakers"].items():
        book_odds = {}

        # Moneyline (h2h)
        if "h2h" in bk_data["markets"]:
            for outcome in bk_data["markets"]["h2h"]:
                side = "home" if outcome["name"] == game_data["home_team"] else "away"
                book_odds[f"ml_{side}"] = outcome["price"]

                current_best = best["moneyline"][side]
                if current_best is None or outcome["price"] > current_best["price"]:
                    best["moneyline"][side] = {
                        "price": outcome["price"],
                        "book": bk_key,
                        "decimal": american_to_decimal(outcome["price"]),
                        "implied_prob": american_to_implied_prob(outcome["price"]),
                    }

        # Spread (puck line)
        if "spreads" in bk_data["markets"]:
            for outcome in bk_data["markets"]["spreads"]:
                side = "home" if outcome["name"] == game_data["home_team"] else "away"
                point = outcome.get("point", 0)
                book_odds[f"spread_{side}"] = {
                    "price": outcome["price"],
                    "point": point,
                }

                current_best = best["spread"][side]
                if current_best is None or outcome["price"] > current_best["price"]:
                    best["spread"][side] = {
                        "price": outcome["price"],
                        "point": point,
                        "book": bk_key,
                        "decimal": american_to_decimal(outcome["price"]),
                        "implied_prob": american_to_implied_prob(outcome["price"]),
                    }

        # Totals (over/under)
        if "totals" in bk_data["markets"]:
            for outcome in bk_data["markets"]["totals"]:
                side = "over" if outcome["name"] == "Over" else "under"
                point = outcome.get("point", 0)
                book_odds[f"total_{side}"] = {
                    "price": outcome["price"],
                    "point": point,
                }

                current_best = best["total"][side]
                if current_best is None or outcome["price"] > current_best["price"]:
                    best["total"][side] = {
                        "price": outcome["price"],
                        "point": point,
                        "book": bk_key,
                        "decimal": american_to_decimal(outcome["price"]),
                        "implied_prob": american_to_implied_prob(outcome["price"]),
                    }

        # Store theScore specifically
        if bk_key == "thescore":
            best["thescore"] = book_odds

        best["all_books"][bk_key] = book_odds

    return best


def get_consensus_no_vig_odds(game_data: dict) -> dict:
    """
    Calculate consensus 'fair' (no-vig) probabilities by averaging
    across sharp bookmakers. This gives us a market-implied true probability.
    """
    sharp_books = ["pinnacle", "betcris", "bovada"]  # known sharp books

    ml_home_probs = []
    ml_away_probs = []
    total_over_probs = []
    spread_home_probs = []
    total_line = None
    spread_line = None

    for bk_key, bk_data in game_data["bookmakers"].items():
        # Moneyline
        if "h2h" in bk_data["markets"]:
            probs = {}
            for outcome in bk_data["markets"]["h2h"]:
                side = "home" if outcome["name"] == game_data["home_team"] else "away"
                probs[side] = american_to_implied_prob(outcome["price"])

            # Remove vig by normalizing
            total_prob = sum(probs.values())
            if total_prob > 0:
                if "home" in probs:
                    ml_home_probs.append(probs["home"] / total_prob)
                if "away" in probs:
                    ml_away_probs.append(probs["away"] / total_prob)

        # Totals
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

        # Spreads
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
        "n_books_spread": len(spread_home_probs),
    }


# Team name mapping: The Odds API uses full names, NHL API uses abbreviations
TEAM_NAME_TO_ABBREV = {
    "Anaheim Ducks": "ANA",
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
    "St Louis Blues": "STL",
    "Tampa Bay Lightning": "TBL",
    "Toronto Maple Leafs": "TOR",
    "Utah Hockey Club": "UTA",
    "Vancouver Canucks": "VAN",
    "Vegas Golden Knights": "VGK",
    "Washington Capitals": "WSH",
    "Winnipeg Jets": "WPG",
    # Arizona moved to Utah
    "Arizona Coyotes": "UTA",
}


def team_name_to_abbrev(name: str) -> str:
    """Convert full team name to NHL abbreviation."""
    return TEAM_NAME_TO_ABBREV.get(name, name)


if __name__ == "__main__":
    try:
        print("Fetching NHL odds...")
        raw = fetch_nhl_odds()
        parsed = parse_odds(raw)
        print(f"\nFound {len(parsed)} games with odds:\n")

        for game in parsed:
            home = game["home_team"]
            away = game["away_team"]
            best = get_best_odds(game)
            consensus = get_consensus_no_vig_odds(game)

            print(f"{away} @ {home}")
            if best["moneyline"]["home"]:
                print(f"  ML: {home} {best['moneyline']['home']['price']:+d} "
                      f"({best['moneyline']['home']['book']}) | "
                      f"{away} {best['moneyline']['away']['price']:+d} "
                      f"({best['moneyline']['away']['book']})")
            if best["spread"]["home"]:
                print(f"  Spread: {home} {best['spread']['home']['point']:+.1f} "
                      f"{best['spread']['home']['price']:+d}")
            if best["total"]["over"]:
                print(f"  Total: O/U {best['total']['over']['point']} | "
                      f"O {best['total']['over']['price']:+d} "
                      f"U {best['total']['under']['price']:+d}")
            print(f"  Fair odds: {home} {consensus['home_win_prob']:.1%} / "
                  f"{away} {consensus['away_win_prob']:.1%}")
            print()

    except ValueError as e:
        print(f"Setup needed: {e}")
