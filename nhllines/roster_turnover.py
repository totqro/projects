"""
Offseason roster turnover — a gameScore-based stand-in for real WAR.
=====================================================================
Elo's season-boundary reversion (SEASON_REVERSION, elo_baseline.py) regresses
every team a fixed 1/3 of the way back toward 1500 regardless of what
actually happened on the roster over the summer — a team that lost its top
line and a team that kept its whole roster get treated identically. This
module measures the roster change directly: who left, who arrived, and how
good those players were, so that signal can eventually be tested as an input
alongside (or instead of) the blanket reversion.

This is deliberately NOT real hockey WAR. Building an actual wins-above-
replacement model is a large, disputed research project on its own (see the
conversation this module came out of) — professional analytics shops don't
agree with each other on methodology. What's used here is MoneyPuck's public
`gameScore` — a simple, established box-score-derived index (Rob Vollman's
formula: weighted goals/assists/shots/blocks/etc.), not a replacement-level
value stat. Treat every number here as "roughly how productive was this
player," not "how many wins was this player worth."

Nothing here is wired into main.py or elo_baseline.py. This is the
measurement step — see the docstring on `net_gamescore_change()` for what
would need to happen before this became a real model input.

Usage:
    python roster_turnover.py --team SJS --from-season 20242025 --to-season 20252026
    python roster_turnover.py --to-season 20252026          # every team, ranked
"""

import argparse
import csv
import io
import json
import time
from collections import defaultdict
from pathlib import Path

import requests

from src.data.historical_dataset import fetch_team_season_schedule
from src.data.nhl_data import CACHE_DIR, _get_cached, _set_cache

API = "https://api-web.nhle.com/v1"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; nhllines-research/1.0)"}

# The boxscore endpoint rate-limits aggressively under any real request
# volume. Verified the hard way: an unpaced, no-retry version of this module
# lost 1058 of ~1300 requests to 429s in one run, silently producing a
# "roster" with a median of 7 games played per player (should be 50-80) —
# not a partial result, a wrong one, because a failed fetch and a real
# "didn't play" both looked like zero data. BASE_REQUEST_DELAY paces every
# request whether it succeeds or not; _fetch_boxscore retries a 429 with
# backoff rather than treating it as "no data for this game."
BASE_REQUEST_DELAY = 0.3
MAX_RETRIES = 6


def _fetch_boxscore(game_id) -> dict:
    """GET one game's boxscore, retrying on 429 with exponential backoff
    (honoring Retry-After if the server sends one) instead of giving up
    after a single failed attempt. Raises on genuine, non-429 failures or
    once retries are exhausted — callers must not treat that the same as a
    real "game has no data" case (see the module docstring's incident)."""
    delay = 1.0
    for attempt in range(MAX_RETRIES):
        resp = requests.get(f"{API}/gamecenter/{game_id}/boxscore", timeout=20)
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else delay
            time.sleep(min(wait, 30))
            delay *= 2
            continue
        resp.raise_for_status()
        return resp.json()
    resp.raise_for_status()  # retries exhausted — raise the last 429, don't swallow it


NHL_TEAMS = [
    "ANA", "ARI", "BOS", "BUF", "CAR", "CBJ", "CGY", "CHI",
    "COL", "DAL", "DET", "EDM", "FLA", "LAK", "MIN", "MTL",
    "NJD", "NSH", "NYI", "NYR", "OTT", "PHI", "PIT", "SEA",
    "SJS", "STL", "TBL", "TOR", "UTA", "VAN", "VGK", "WPG", "WSH",
]


def _skaters_csv_path(year: int) -> Path:
    return CACHE_DIR / f"moneypuck_skaters_{year}.csv"


def load_gamescores(year: int) -> dict:
    """{playerId: (name, team, games_played, total_gameScore)} for a season,
    filtered to situation='all' (full-season, all-strengths aggregate).

    gameScore is a season TOTAL, not a per-game rate — verified empirically:
    a 1-game call-up scores ~1.3, not a full-season-equivalent number. That
    means a player who only played half a season already contributes roughly
    half the total of a similar player who played the whole thing, with no
    extra weighting needed on top.

    KNOWN LIMITATION: MoneyPuck's file attributes a player's ENTIRE season to
    ONE team, even if they were traded mid-season — confirmed empirically
    (zero players have multiple team rows in a season's file; a known
    mid-season trade still shows the player under only one team). There is no
    way, from this data source, to give the selling team credit only for the
    games played before a mid-season trade. Accepted as a gap, not silently
    papered over."""
    path = _skaters_csv_path(year)
    if not path.exists():
        url = f"https://moneypuck.com/moneypuck/playerData/seasonSummary/{year}/regular/skaters.csv"
        resp = requests.get(url, headers=HEADERS, timeout=120)
        resp.raise_for_status()
        path.write_text(resp.text)

    scores = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            if row["situation"] != "all":
                continue
            pid = int(row["playerId"])
            scores[pid] = {
                "name": row["name"],
                "team": row["team"],
                "games_played": float(row["games_played"] or 0.0),
                "gameScore": float(row["gameScore"] or 0.0),
            }
    return scores


def get_roster_player_ids(team: str, season: str) -> dict:
    """{playerId: name} for a team's skaters (forwards + defensemen; goalies
    excluded — gameScore isn't a goalie stat) in a given season, via the
    /roster/{team}/{season} endpoint.

    KNOWN UNRELIABLE — kept only for reference/comparison. Verified: for a
    season that had JUST finished (2025-26, queried ~3 months after the
    season ended) this returned only 17 total players, missing a confirmed
    real trade (Eklund). For older seasons (2021-22, 2022-23) it returned
    40+ players — over-inclusive, likely counting every AHL call-up who
    ever touched the org that year. It only looked plausible for seasons
    roughly 1-2 years old (2023-24, 2024-25). get_team_boxscore_roster()
    below replaces this with ground truth that doesn't depend on how
    recently the season ended."""
    resp = requests.get(f"{API}/roster/{team}/{season}", timeout=20)
    if resp.status_code == 404:
        return {}
    resp.raise_for_status()
    data = resp.json()
    out = {}
    for group in ("forwards", "defensemen"):
        for p in data.get(group, []):
            name = f"{p['firstName']['default']} {p['lastName']['default']}"
            out[p["id"]] = name
    return out


def get_team_boxscore_roster(team: str, season: str, verbose: bool = False) -> dict:
    """Ground-truth {playerId: {"name": str, "games_played": int}} for a
    team's skaters in a season, built by scanning every completed game on
    THAT TEAM'S OWN schedule (~82 games, not the full league) and recording
    who actually dressed, via the same boxscore endpoint this project
    already trusts for goalie starters.

    This replaces get_roster_player_ids() above for two reasons, both
    verified empirically:
      1. It's available immediately, with no settling lag — a season that
         ended yesterday has exactly as complete a boxscore record as one
         that ended five years ago.
      2. It correctly splits a mid-season-traded player's games between the
         team(s) they actually played for. MoneyPuck's season-summary file
         attributes a traded player's WHOLE season to a single team
         (verified: zero players have multiple team rows in one season's
         file); this fixes the team-attribution side of that gap, though
         the underlying VALUE (gameScore) still can't be split the same
         way — see load_gamescores()'s docstring for that remaining limit.

    Cached per (game, team) — a completed game's boxscore never changes, so
    once fetched, rebuilding a roster for the same team/season is free."""
    games = fetch_team_season_schedule(team, season)
    counts = defaultdict(lambda: {"name": None, "games_played": 0})

    for g in games:
        if g.get("gameType") != 2 or g.get("gameState") not in ("OFF", "FINAL"):
            continue
        gid = g["id"]
        cache_key = f"boxscore_skaters_{gid}_{team}"
        cached = _get_cached(cache_key, max_age_hours=24 * 365)
        if cached is None:
            try:
                data = _fetch_boxscore(gid)
            except Exception as e:
                if verbose:
                    print(f"  ⚠ boxscore fetch failed for game {gid} after "
                          f"{MAX_RETRIES} retries: {e}")
                time.sleep(BASE_REQUEST_DELAY)
                continue
            time.sleep(BASE_REQUEST_DELAY)

            pbgs = data.get("playerByGameStats", {})
            is_home = data.get("homeTeam", {}).get("abbrev") == team
            side = pbgs.get("homeTeam" if is_home else "awayTeam", {})
            appeared = []
            for group in ("forwards", "defense"):
                for p in side.get(group, []):
                    appeared.append((p["playerId"], p.get("name", {}).get("default", "?")))
            cached = appeared
            _set_cache(cache_key, cached)

        for pid, name in cached:
            counts[pid]["name"] = name
            counts[pid]["games_played"] += 1

    return dict(counts)


def _league_season_cache_path(season: str) -> Path:
    return CACHE_DIR / f"league_boxscore_rosters_{season}.json"


def build_league_boxscore_rosters(season: str, verbose: bool = True) -> dict:
    """{playerId: {"name": str, "teams": {team_abbrev: games_played}}} for
    EVERY skater across the WHOLE LEAGUE in one season.

    This is what get_team_boxscore_roster() can't give you: an ARRIVING
    player's true multi-team split. That function only looks at one team's
    own games, so a player who wasn't yet on that team has no boxscore
    record there — arrivals fall back to MoneyPuck's season file, which
    attributes a mid-season-traded player's value to a single team. This
    function fetches every game ONCE (not once per team — a season has
    ~1300 unique games, not 2600) and extracts both sides at once, giving
    an exact per-team games-played breakdown for every player in the league,
    which get_arrival_team_split() below uses to fix that gap.

    Expensive (~1300 requests, several minutes) — cached to disk as ONE file
    per season (not per-game like the single-team function), since this is
    meant to be built once and reused, not rebuilt per team lookup."""
    cache_path = _league_season_cache_path(season)
    if cache_path.exists():
        return json.loads(cache_path.read_text())

    from src.data.historical_dataset import fetch_season_games_full
    games = fetch_season_games_full(season, verbose=verbose)

    players = defaultdict(lambda: {"name": None, "teams": defaultdict(int)})
    n = len(games)
    failed = 0
    for i, g in enumerate(games):
        gid = g["id"]
        cache_key = f"boxscore_league_{gid}"
        cached = _get_cached(cache_key, max_age_hours=24 * 365)
        if cached is None:
            try:
                data = _fetch_boxscore(gid)
            except Exception as e:
                failed += 1
                if verbose:
                    print(f"  ⚠ boxscore fetch failed for game {gid} after "
                          f"{MAX_RETRIES} retries: {e}")
                time.sleep(BASE_REQUEST_DELAY)
                continue
            time.sleep(BASE_REQUEST_DELAY)

            pbgs = data.get("playerByGameStats", {})
            home_team = data.get("homeTeam", {}).get("abbrev")
            away_team = data.get("awayTeam", {}).get("abbrev")
            cached = {"home_team": home_team, "away_team": away_team,
                     "home": [], "away": []}
            for side_key, out_key in (("homeTeam", "home"), ("awayTeam", "away")):
                side = pbgs.get(side_key, {})
                for group in ("forwards", "defense"):
                    for p in side.get(group, []):
                        cached[out_key].append(
                            (p["playerId"], p.get("name", {}).get("default", "?")))
            _set_cache(cache_key, cached)

        for pid, name in cached["home"]:
            players[pid]["name"] = name
            players[pid]["teams"][cached["home_team"]] += 1
        for pid, name in cached["away"]:
            players[pid]["name"] = name
            players[pid]["teams"][cached["away_team"]] += 1

        if verbose and (i + 1) % 200 == 0:
            print(f"  ...{i + 1}/{n} games processed")

    # Refuse to persist a degraded result. This exists BECAUSE a prior run of
    # this exact function lost 1058/1300+ games to unretried 429s and wrote
    # the corrupted result to disk anyway — every later call silently trusted
    # a season-level cache file that looked complete but wasn't. A high
    # failure rate now raises instead of caching, so a bad run has to be
    # investigated, not accidentally treated as ground truth forever.
    fail_rate = failed / n if n else 0.0
    if fail_rate > 0.05:
        raise RuntimeError(
            f"{failed}/{n} games ({fail_rate:.0%}) failed to fetch for {season} — "
            f"refusing to cache a result this incomplete. Re-run; only the failed "
            f"games need to be re-fetched (successful ones are already cached "
            f"per-game under boxscore_league_<id>).")

    result = {str(pid): {"name": e["name"], "teams": dict(e["teams"])}
             for pid, e in players.items()}
    cache_path.write_text(json.dumps(result))
    if verbose:
        print(f"  {n - failed}/{n} games fetched successfully "
              f"({failed} failed, {fail_rate:.1%})")
    return result


def get_arrival_team_split(league_rosters: dict, player_id: int) -> dict:
    """{team: games_played} for one player across the whole league in the
    season league_rosters was built for — the accurate, per-team picture
    net_gamescore_change() falls back to MoneyPuck's single-team attribution
    for today."""
    entry = league_rosters.get(str(player_id))
    return entry["teams"] if entry else {}


def net_gamescore_change(team: str, from_season: str, to_season: str,
                         min_games_played: int = 15,
                         league_rosters: dict = None) -> dict:
    """Roster diff for one team between two seasons, plus the net gameScore
    swing. `from_season`'s gameScore values are used for BOTH departed and
    arrived players — departed players' value is what the team lost by
    definition; arrived players are valued at what they did last season
    (wherever they played), which is the only prior data available at the
    point this would need to inform a rating going into `to_season`.

    `min_games_played` filters out two-way/AHL-shuttle noise. Roster
    MEMBERSHIP and GAMES-PLAYED come from get_team_boxscore_roster() —
    ground truth from this team's own boxscores, not the settling-dependent
    /roster endpoint — so a departing player's games-played filter reflects
    exactly how much THIS team actually got from them, correctly excluding
    e.g. a black-ace call-up who dressed for 2 games even if that same
    player was a full-time regular somewhere else.

    A player with ZERO games in the relevant data is a genuine rookie
    (Celebrini, Will Smith — see the module's real test output), not noise,
    and is never filtered — only a player with SOME games below the
    threshold is treated as a call-up.

    `league_rosters`, if given (from build_league_boxscore_rosters()), adds
    a `prior_teams` breakdown to every departed/arrived entry — e.g. a
    departure who was traded mid-season shows exactly how many games they
    played for THIS team vs wherever else. Verified against two independent
    real trades (Hertl 2023-24: 48 SJS + 6 VGK; Monahan: 49 MTL + 34 WPG)
    that MoneyPuck's games_played is already an accurate COMBINED total
    across teams — so this does NOT change the filter or value numbers,
    which were already correct. What it adds is transparency: which team(s)
    actually contributed, not a numeric correction.

    No extra weighting by games played beyond the threshold: gameScore is
    already a season TOTAL, not a rate (verified in load_gamescores()'s
    docstring), so a partial-season player already contributes proportionally
    less without any further adjustment.

    Before this becomes a real Elo input: the whole point of building this
    was to test it, not assume it helps. That means running it across many
    past offseasons and checking — the same way model_gate.py's --loso does
    for the win model — whether teams with a big positive net_gamescore
    swing actually outperform what Elo's blanket reversion alone would have
    predicted for them the following season. That test hasn't been run yet.
    """
    old_roster = get_team_boxscore_roster(team, from_season)
    new_roster = get_team_boxscore_roster(team, to_season)

    old_year = int(from_season[:4])
    gamescores = load_gamescores(old_year)

    # Departures: filtered on THIS team's own accurate games_played.
    old_roster = {pid: entry for pid, entry in old_roster.items()
                 if entry["games_played"] >= min_games_played}
    # Arrivals: no boxscore data exists for a player before they join this
    # team, so the filter falls back to MoneyPuck's (already-verified-accurate
    # total) attribution.
    def _is_arrival_noise(pid) -> bool:
        entry = gamescores.get(pid)
        return entry is not None and 0 < entry["games_played"] < min_games_played
    new_roster = {pid: entry for pid, entry in new_roster.items()
                 if not _is_arrival_noise(pid)}

    departed_ids = set(old_roster) - set(new_roster)
    arrived_ids = set(new_roster) - set(old_roster)
    kept_ids = set(old_roster) & set(new_roster)

    def _lookup(pid, roster):
        entry = gamescores.get(pid)
        name = entry["name"] if entry else roster[pid]["name"]
        gs = entry["gameScore"] if entry else 0.0
        out = {"player_id": pid, "name": name, "prior_season_gameScore": gs}
        if league_rosters is not None:
            split = get_arrival_team_split(league_rosters, pid)
            if len(split) > 1:
                out["prior_teams"] = split
        return out

    departed = [_lookup(pid, old_roster) for pid in departed_ids]
    arrived = [_lookup(pid, new_roster) for pid in arrived_ids]
    departed.sort(key=lambda p: -p["prior_season_gameScore"])
    arrived.sort(key=lambda p: -p["prior_season_gameScore"])

    departed_total = sum(p["prior_season_gameScore"] for p in departed)
    arrived_total = sum(p["prior_season_gameScore"] for p in arrived)

    return {
        "team": team,
        "from_season": from_season,
        "to_season": to_season,
        "n_kept": len(kept_ids),
        "n_departed": len(departed),
        "n_arrived": len(arrived),
        "departed_gameScore_total": departed_total,
        "arrived_gameScore_total": arrived_total,
        "net_gameScore_change": arrived_total - departed_total,
        "departed": departed,
        "arrived": arrived,
    }


def print_team_report(result: dict) -> None:
    print("=" * 78)
    print(f"  {result['team']} — roster change, {result['from_season']} -> {result['to_season']}")
    print("=" * 78)
    print(f"  Kept: {result['n_kept']}   Departed: {result['n_departed']}   "
          f"Arrived: {result['n_arrived']}")
    print(f"  Departed total prior-season gameScore: {result['departed_gameScore_total']:.1f}")
    print(f"  Arrived total prior-season gameScore:  {result['arrived_gameScore_total']:.1f}")
    print(f"  Net change: {result['net_gameScore_change']:+.1f}")
    print("-" * 78)
    def _fmt_split(p):
        split = p.get("prior_teams")
        if not split:
            return ""
        return "  (" + ", ".join(f"{t}:{g}" for t, g in
                                 sorted(split.items(), key=lambda kv: -kv[1])) + ")"

    if result["departed"]:
        print("  Notable departures (by prior-season gameScore):")
        for p in result["departed"][:8]:
            print(f"    {p['name']:<24}{p['prior_season_gameScore']:>7.1f}{_fmt_split(p)}")
    if result["arrived"]:
        print("  Notable arrivals (by prior-season gameScore):")
        for p in result["arrived"][:8]:
            print(f"    {p['name']:<24}{p['prior_season_gameScore']:>7.1f}{_fmt_split(p)}")
    print("-" * 78)


def print_league_report(results: list) -> None:
    ranked = sorted(results, key=lambda r: r["net_gameScore_change"])
    print("=" * 78)
    print(f"  LEAGUE-WIDE OFFSEASON ROSTER CHANGE — {ranked[0]['from_season']} -> "
          f"{ranked[0]['to_season']}")
    print("=" * 78)
    print(f"{'Team':<8}{'Departed':>10}{'Arrived':>10}{'Net change':>13}")
    print("-" * 78)
    for r in ranked:
        print(f"{r['team']:<8}{r['departed_gameScore_total']:>10.1f}"
              f"{r['arrived_gameScore_total']:>10.1f}{r['net_gameScore_change']:>+13.1f}")
    print("-" * 78)
    print("  Most net gameScore LOST over the summer (biggest downgrade):")
    for r in ranked[:3]:
        print(f"    {r['team']}: {r['net_gameScore_change']:+.1f}")
    print("  Most net gameScore GAINED over the summer (biggest upgrade):")
    for r in ranked[-3:][::-1]:
        print(f"    {r['team']}: {r['net_gameScore_change']:+.1f}")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--team", default=None,
                        help="Single team to report on in detail (default: every team, ranked)")
    parser.add_argument("--from-season", default="20242025")
    parser.add_argument("--to-season", default="20252026")
    parser.add_argument("--min-games-played", type=int, default=15,
                        help="Below this many games played in from_season, a "
                             "player is dropped as two-way/AHL-shuttle noise "
                             "(default: 15). Players with ZERO games (true "
                             "rookies) are never filtered by this.")
    parser.add_argument("--with-team-splits", action="store_true",
                        help="Build the full league-wide boxscore roster "
                             "(~1300 requests, several minutes, cached after "
                             "first run) to show which team(s) each departure/"
                             "arrival actually came from. Doesn't change any "
                             "numbers — see net_gamescore_change()'s docstring.")
    parser.add_argument("--json", dest="json_path", default=None)
    args = parser.parse_args()

    league_rosters = None
    if args.with_team_splits:
        league_rosters = build_league_boxscore_rosters(args.from_season)

    if args.team:
        result = net_gamescore_change(args.team, args.from_season, args.to_season,
                                      min_games_played=args.min_games_played,
                                      league_rosters=league_rosters)
        print_team_report(result)
        if args.json_path:
            Path(args.json_path).write_text(json.dumps(result, indent=2))
        return 0

    results = []
    for team in NHL_TEAMS:
        r = net_gamescore_change(team, args.from_season, args.to_season,
                                 min_games_played=args.min_games_played,
                                 league_rosters=league_rosters)
        if r["n_kept"] + r["n_departed"] + r["n_arrived"] == 0:
            continue  # team didn't exist in from_season (e.g. UTA before 2024-25)
        results.append(r)
        time.sleep(0.1)  # be polite to the roster endpoint across 32 calls
    print_league_report(results)
    if args.json_path:
        Path(args.json_path).write_text(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
