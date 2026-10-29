"""
ESPN Odds Module
Fetches pre-game lines from ESPN's public scoreboard feed: no key, no quota.

ESPN carries a single book (DraftKings) per game, so this is a market price,
not a line shop. It is the keyless fallback for The Odds API, and the only
source the market snapshot jobs use: devigging one sharp-enough book is close
to the multi-book consensus, and a snapshot never has to compete with the
daily predictions for monthly credits.

Games come back in The Odds API's /odds shape (id, commence_time, home_team,
away_team, bookmakers -> markets -> outcomes), so parse_odds() and everything
downstream of it work unchanged. Kept identical in nhllines/ and mlblines/.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard"

# Odds API sport key -> ESPN sport/league path
ESPN_PATHS = {
    "icehockey_nhl": "hockey/nhl",
    "baseball_mlb": "baseball/mlb",
}

ET = ZoneInfo("America/New_York")


def _american(value) -> int | None:
    """ESPN prices are strings: "-180", "+150", "EVEN", or "OFF" when pulled."""
    if value is None:
        return None
    text = str(value).strip().upper()
    if text == "EVEN":
        return 100
    try:
        return int(float(text.replace("+", "")))
    except ValueError:
        return None


def _line(value) -> float | None:
    """Spread lines arrive as "-1.5"; totals as "o6.5" / "u6.5"."""
    if value is None:
        return None
    try:
        return float(str(value).strip().lstrip("ouOU"))
    except ValueError:
        return None


def _side(block: dict) -> dict:
    """The current price. ESPN labels it "close" even before the game: it is
    the latest line, and "open" is the opener."""
    return (block or {}).get("close") or {}


def _markets(odds: dict, home: str, away: str) -> list:
    markets = []

    ml = odds.get("moneyline") or {}
    home_ml, away_ml = _american(_side(ml.get("home")).get("odds")), _american(_side(ml.get("away")).get("odds"))
    if home_ml is not None and away_ml is not None:
        markets.append({"key": "h2h", "outcomes": [
            {"name": home, "price": home_ml},
            {"name": away, "price": away_ml},
        ]})

    ps = odds.get("pointSpread") or {}
    home_ps, away_ps = _side(ps.get("home")), _side(ps.get("away"))
    home_price, away_price = _american(home_ps.get("odds")), _american(away_ps.get("odds"))
    home_point, away_point = _line(home_ps.get("line")), _line(away_ps.get("line"))
    if None not in (home_price, away_price, home_point, away_point):
        markets.append({"key": "spreads", "outcomes": [
            {"name": home, "price": home_price, "point": home_point},
            {"name": away, "price": away_price, "point": away_point},
        ]})

    tot = odds.get("total") or {}
    over, under = _side(tot.get("over")), _side(tot.get("under"))
    over_price, under_price = _american(over.get("odds")), _american(under.get("odds"))
    point = _line(over.get("line"))
    if point is None:
        point = odds.get("overUnder")
    if None not in (over_price, under_price, point):
        markets.append({"key": "totals", "outcomes": [
            {"name": "Over", "price": over_price, "point": float(point)},
            {"name": "Under", "price": under_price, "point": float(point)},
        ]})

    return markets


def fetch_espn_odds(sport: str, days: int = 2) -> list:
    """Pre-game odds for `sport` (an Odds API sport key) over the next `days`
    ET dates, in The Odds API's /odds response shape.

    Games already underway are dropped: ESPN pulls live games' odds anyway,
    and a snapshot or a pick must only ever see a pre-game price.
    """
    path = ESPN_PATHS.get(sport)
    if path is None:
        raise ValueError(f"No ESPN scoreboard mapped for sport '{sport}'")

    today = datetime.now(ET).date()
    games, seen = [], set()
    for offset in range(days):
        date = (today + timedelta(days=offset)).strftime("%Y%m%d")
        resp = requests.get(ESPN_SCOREBOARD.format(path=path),
                            params={"dates": date}, timeout=15)
        resp.raise_for_status()

        for event in resp.json().get("events", []):
            comp = (event.get("competitions") or [{}])[0]
            if event["id"] in seen or comp.get("status", {}).get("type", {}).get("state") != "pre":
                continue
            teams = {c.get("homeAway"): c["team"]["displayName"] for c in comp.get("competitors", [])}
            if "home" not in teams or "away" not in teams:
                continue

            bookmakers = []
            for odds in comp.get("odds") or []:
                markets = _markets(odds, teams["home"], teams["away"])
                if not markets:
                    continue
                title = (odds.get("provider") or {}).get("name") or "ESPN"
                bookmakers.append({
                    "key": title.lower().replace(" ", ""),
                    "title": title,
                    "markets": markets,
                })
            if not bookmakers:
                continue

            # "2026-10-28T23:30Z" -> the Odds API's "2026-10-28T23:30:00Z"
            start = datetime.fromisoformat(event["date"].replace("Z", "+00:00"))
            seen.add(event["id"])
            games.append({
                "id": f"espn-{event['id']}",
                "sport_key": sport,
                "commence_time": start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "home_team": teams["home"],
                "away_team": teams["away"],
                "bookmakers": bookmakers,
            })

    return games
