"""
Point-in-Time Multi-Season Historical Dataset Builder
=====================================================
Fixes the training-data leakage diagnosed in July 2026: every feature for a
historical game is computed ONLY from games played before that game's date.

Data source: free NHL API (api-web.nhle.com), per-team season schedules
(/v1/club-schedule-season/{TEAM}/{season}) — 32 requests per season, cached.

Output rows contain:
- Point-in-time season-to-date stats (win%, points%, GF/G, GA/G, home/road splits)
- Point-in-time last-10 form (win%, GF, GA)
- Rest days and back-to-back flags derived from the schedule
- Weighted streak, form trend (last 5 vs previous 5)
- Point-in-time head-to-head (prior meetings only, across seasons)
- Labels: home_win, total_goals, goal_diff, went_ot

No current-season standings, no current goalie/advanced stats stamped onto
past games, no features unavailable at prediction time.
"""

import csv
import time
from collections import deque, defaultdict
from datetime import datetime
from pathlib import Path

import requests

from .nhl_data import NHL_TEAMS, _get_cached, _set_cache, BASE_URL
from .moneypuck_data import load_moneypuck_xg

# MoneyPuck shot-level xG data is only published for these season-start
# years (see moneypuck_data.py). Games in a covered season MUST join onto
# MoneyPuck data (hard failure if not — see build_point_in_time_rows);
# games outside this range (a season MoneyPuck hasn't published yet) fall
# back to neutral xG-feature defaults, same as the goalie-priors pattern.
MONEYPUCK_YEARS = [2022, 2023, 2024, 2025]
MONEYPUCK_SEASONS = frozenset(f"{y}{y + 1}" for y in MONEYPUCK_YEARS)

# A season that ended more than this long ago never changes — cache forever.
_COMPLETED_SEASON_CACHE_HOURS = 24 * 365 * 10
_CURRENT_SEASON_CACHE_HOURS = 12

# League-average priors for a goalie with no recorded starts yet (rookie,
# recent call-up, or a game whose boxscore couldn't be fetched).
DEFAULT_GOALIE_SV_PCT = 0.905
DEFAULT_GOALIE_GAA = 2.75


def current_season() -> str:
    """
    The NHL season a game played now (or next) belongs to: from July 1 the
    upcoming YYYY(YYYY+1) season, before that the season ending this year.
    """
    now = datetime.now()
    start = now.year if now.month >= 7 else now.year - 1
    return f"{start}{start + 1}"


def seasons_through_current(first: str = "20222023") -> list:
    """
    Every season from `first` through the current one, inclusive. Used as the
    rolling default season list so live Elo ratings, the dataset builder, and
    the calibrator automatically pick up a new season when it starts instead
    of freezing on a hardcoded list.
    """
    first_start = int(first[:4])
    cur_start = int(current_season()[:4])
    return [f"{y}{y + 1}" for y in range(first_start, cur_start + 1)]


def _season_end_year(season: str) -> int:
    return int(season[4:])


def _season_is_complete(season: str) -> bool:
    """A season string like '20242025' is surely complete after July 1 of its end year."""
    now = datetime.now()
    end_year = _season_end_year(season)
    return (now.year, now.month) >= (end_year, 7)


def fetch_team_season_schedule(team: str, season: str) -> list:
    """
    Fetch one team's full season schedule from the NHL API.
    Returns raw game dicts, or [] if the team didn't exist that season (404).
    """
    cache_key = f"club_season_{team}_{season}"
    max_age = (_COMPLETED_SEASON_CACHE_HOURS if _season_is_complete(season)
               else _CURRENT_SEASON_CACHE_HOURS)
    cached = _get_cached(cache_key, max_age_hours=max_age)
    if cached is not None:
        return cached

    url = f"{BASE_URL}/club-schedule-season/{team}/{season}"
    resp = requests.get(url, timeout=20)
    if resp.status_code == 404:
        _set_cache(cache_key, [])
        return []
    resp.raise_for_status()
    games = resp.json().get("games", [])
    _set_cache(cache_key, games)
    time.sleep(0.25)  # be polite to the free API
    return games


def fetch_season_games_full(season: str, verbose: bool = True) -> list:
    """
    Fetch ALL completed regular-season games for a season (~1300 games).
    Deduplicates across the 32 per-team schedules by game id.
    """
    seen = {}
    for team in NHL_TEAMS:
        try:
            raw_games = fetch_team_season_schedule(team, season)
        except Exception as e:
            if verbose:
                print(f"  ⚠ {team} {season}: {e}")
            continue

        for g in raw_games:
            gid = g.get("id")
            if gid in seen:
                continue
            if g.get("gameType") != 2:  # regular season only
                continue
            if g.get("gameState") not in ("OFF", "FINAL"):
                continue
            home = g.get("homeTeam", {})
            away = g.get("awayTeam", {})
            home_score = home.get("score")
            away_score = away.get("score")
            if home_score is None or away_score is None:
                continue

            seen[gid] = {
                "id": gid,
                "season": season,
                "date": g.get("gameDate", ""),
                "home_team": home.get("abbrev", ""),
                "away_team": away.get("abbrev", ""),
                "home_score": home_score,
                "away_score": away_score,
                "home_win": home_score > away_score,
                "total_goals": home_score + away_score,
                "goal_diff": home_score - away_score,
                # REG / OT / SO — loser earns a point in OT/SO
                "last_period_type": g.get("gameOutcome", {}).get("lastPeriodType", "REG"),
            }

    games = sorted(seen.values(), key=lambda g: (g["date"], g["id"]))
    if verbose:
        print(f"  ✓ {season}: {len(games)} completed regular-season games")
    return games


def _parse_toi(toi) -> float:
    try:
        mins, secs = toi.split(":")
        return int(mins) + int(secs) / 60
    except (ValueError, AttributeError):
        return 0.0


def _goalie_line(g: dict) -> dict:
    return {
        "id": g.get("playerId"),
        "name": g.get("name", {}).get("default", ""),
        "shots_against": g.get("shotsAgainst", 0) or 0,
        "saves": g.get("saves", 0) or 0,
        "goals_against": g.get("goalsAgainst", 0) or 0,
        "minutes": _parse_toi(g.get("toi", "0:00")),
    }


def _extract_starter(team_stats: dict) -> dict:
    """Pull the starting goalie's line out of one team's boxscore stats block."""
    goalies = team_stats.get("goalies", [])
    for g in goalies:
        if g.get("starter"):
            return _goalie_line(g)
    # No starter tag (older seasons / data gaps): fall back to the goalie who
    # played the most minutes rather than silently degrading to league priors.
    lines = [_goalie_line(g) for g in goalies]
    lines = [l for l in lines if l["minutes"] > 0]
    if lines:
        return max(lines, key=lambda l: l["minutes"])
    return None


def fetch_game_starters(game_id) -> tuple:
    """
    Fetch the actual starting goalie for each side of one historical game via
    the NHL API boxscore endpoint (/gamecenter/{id}/boxscore), which tags the
    goalie who started with "starter": true and reports their in-game line.

    Returns (home_starter, away_starter) dicts (id/name/shots_against/saves/
    goals_against/minutes), or (None, None) if the fetch failed or no starter
    was tagged (e.g. very old games).
    """
    cache_key = f"boxscore_starters_{game_id}"
    cached = _get_cached(cache_key, max_age_hours=_COMPLETED_SEASON_CACHE_HOURS)
    if cached is not None:
        return cached.get("home"), cached.get("away")

    try:
        url = f"{BASE_URL}/gamecenter/{game_id}/boxscore"
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None, None

    pbgs = data.get("playerByGameStats", {})
    home = _extract_starter(pbgs.get("homeTeam", {}))
    away = _extract_starter(pbgs.get("awayTeam", {}))
    _set_cache(cache_key, {"home": home, "away": away})
    time.sleep(0.1)  # be polite to the free API
    return home, away


def fetch_all_starters(games: list, verbose: bool = True) -> dict:
    """
    Fetch starting goalies for every game in `games` (one boxscore request per
    game, cached forever once a game is complete). Returns {game_id: (home, away)}.
    """
    starters = {}
    total = len(games)
    for i, g in enumerate(games):
        home, away = fetch_game_starters(g["id"])
        starters[g["id"]] = (home, away)
        if verbose and total and (i + 1) % 200 == 0:
            print(f"  ... starting goalies: {i + 1}/{total} games")
    if verbose:
        found = sum(1 for h, a in starters.values() if h and a)
        print(f"  ✓ Starting goalies found for {found}/{total} games")
    return starters


class _GoalieState:
    """Rolling point-in-time state for one goalie, carried across seasons."""

    def __init__(self):
        self.starts = 0
        self.shots_against = 0
        self.saves = 0
        self.goals_against = 0
        self.minutes = 0.0
        self.recent = deque(maxlen=10)  # (game_sv_pct, game_gaa) per start

    def snapshot(self) -> dict:
        sv_pct = (self.saves / self.shots_against
                  if self.shots_against else DEFAULT_GOALIE_SV_PCT)
        gaa = ((self.goals_against * 60) / self.minutes
               if self.minutes else DEFAULT_GOALIE_GAA)
        if self.recent:
            recent_sv_pct = sum(x[0] for x in self.recent) / len(self.recent)
            recent_gaa = sum(x[1] for x in self.recent) / len(self.recent)
        else:
            recent_sv_pct, recent_gaa = sv_pct, gaa
        return {
            "starts": self.starts,
            "sv_pct": sv_pct,
            "gaa": gaa,
            "recent_sv_pct": recent_sv_pct,
            "recent_gaa": recent_gaa,
        }

    def record(self, shots_against: int, saves: int, goals_against: int, minutes: float):
        self.starts += 1
        self.shots_against += shots_against
        self.saves += saves
        self.goals_against += goals_against
        self.minutes += minutes
        game_sv_pct = saves / shots_against if shots_against else DEFAULT_GOALIE_SV_PCT
        game_gaa = (goals_against * 60) / minutes if minutes else DEFAULT_GOALIE_GAA
        self.recent.append((game_sv_pct, game_gaa))


_DEFAULT_GOALIE_SNAPSHOT = {
    "starts": 0,
    "sv_pct": DEFAULT_GOALIE_SV_PCT,
    "gaa": DEFAULT_GOALIE_GAA,
    "recent_sv_pct": DEFAULT_GOALIE_SV_PCT,
    "recent_gaa": DEFAULT_GOALIE_GAA,
}


class _TeamState:
    """Rolling point-in-time state for one team within one season."""

    def __init__(self):
        self.gp = 0
        self.wins = 0
        self.points = 0
        self.gf = 0
        self.ga = 0
        self.home_gp = 0
        self.home_wins = 0
        self.road_gp = 0
        self.road_wins = 0
        self.last10 = deque(maxlen=10)   # (won, gf, ga)
        self.results = []                # chronological wins (1/0) for trend
        self.last_game_date = None

        # MoneyPuck xG rolling state. xg_gp tracks games with actual xG data
        # (may lag self.gp if MoneyPuck coverage is incomplete for a game);
        # xg_covered_gf/ga are goals-for/against restricted to that same
        # subset, so the luck features (goals - xG) never mix xG-covered and
        # xG-uncovered games.
        self.xg_gp = 0
        self.cum_xgf_raw = 0.0
        self.cum_xga_raw = 0.0
        self.cum_xgf_adj = 0.0
        self.cum_xga_adj = 0.0
        self.cum_hd_xgf = 0.0
        self.xg_covered_gf = 0
        self.xg_covered_ga = 0

    def snapshot(self, game_date: str) -> dict:
        """Features for this team as of BEFORE game_date."""
        gp = self.gp
        form = list(self.last10)
        n_form = len(form)

        rest_days = 3
        b2b = False
        if self.last_game_date:
            try:
                d0 = datetime.strptime(self.last_game_date, "%Y-%m-%d")
                d1 = datetime.strptime(game_date, "%Y-%m-%d")
                rest_days = max((d1 - d0).days, 0)
                b2b = rest_days <= 1
            except ValueError:
                pass

        # Weighted streak over last 10 (recent games weighted higher)
        streak = 0.0
        for j, (won, _, _) in enumerate(form):
            weight = 0.85 ** (n_form - 1 - j)
            streak += weight * (1 if won else -1)

        # Form trend: last 5 vs previous 5
        trend = 0.0
        if len(self.results) >= 10:
            recent = sum(self.results[-5:]) / 5
            prev = sum(self.results[-10:-5]) / 5
            trend = max(-1.0, min(1.0, (recent - prev) * 2))

        # xG features: xgf/xga_per60 use the score/venue-"adjusted" (5v5,
        # score within one) cumulative xG — see moneypuck_data.py — divided
        # by games with xG data (nominal 60-minute games, matching this
        # dataset's per-game rate convention elsewhere). Defaults are
        # neutral league-average-ish priors for teams/seasons with no xG
        # data yet (mirrors the goalie-priors pattern).
        xgf_per60 = self.cum_xgf_adj / self.xg_gp if self.xg_gp else 3.0
        xga_per60 = self.cum_xga_adj / self.xg_gp if self.xg_gp else 3.0
        high_danger_xg_share = (self.cum_hd_xgf / self.cum_xgf_raw
                                 if self.cum_xgf_raw > 0 else 0.4)
        xg_luck_for = (self.xg_covered_gf - self.cum_xgf_raw) if self.xg_gp else 0.0
        xg_luck_against = (self.xg_covered_ga - self.cum_xga_raw) if self.xg_gp else 0.0

        return {
            "gp": gp,
            "win_pct": self.wins / gp if gp else 0.5,
            "points_pct": self.points / (2 * gp) if gp else 0.5,
            "gf_pg": self.gf / gp if gp else 3.0,
            "ga_pg": self.ga / gp if gp else 3.0,
            "home_win_pct": self.home_wins / self.home_gp if self.home_gp else 0.5,
            "road_win_pct": self.road_wins / self.road_gp if self.road_gp else 0.5,
            "form_win_pct": (sum(w for w, _, _ in form) / n_form) if n_form else 0.5,
            "form_gf": (sum(gf for _, gf, _ in form) / n_form) if n_form else 3.0,
            "form_ga": (sum(ga for _, _, ga in form) / n_form) if n_form else 3.0,
            "rest_days": min(rest_days, 7),
            "b2b": 1 if b2b else 0,
            "streak": streak,
            "trend": trend,
            "xgf_per60": xgf_per60,
            "xga_per60": xga_per60,
            "high_danger_xg_share": high_danger_xg_share,
            "xg_luck_for": xg_luck_for,
            "xg_luck_against": xg_luck_against,
        }

    def record(self, game_date: str, won: bool, gf: int, ga: int,
               is_home: bool, lost_in_extra: bool, xg: dict = None):
        self.gp += 1
        self.gf += gf
        self.ga += ga
        if won:
            self.wins += 1
            self.points += 2
        elif lost_in_extra:
            self.points += 1
        if is_home:
            self.home_gp += 1
            self.home_wins += 1 if won else 0
        else:
            self.road_gp += 1
            self.road_wins += 1 if won else 0
        self.last10.append((1 if won else 0, gf, ga))
        self.results.append(1 if won else 0)
        if xg is not None:
            self.xg_gp += 1
            self.cum_xgf_raw += xg["xgf"]
            self.cum_xga_raw += xg["xga"]
            self.cum_xgf_adj += xg["xgf_adj"]
            self.cum_xga_adj += xg["xga_adj"]
            self.cum_hd_xgf += xg["hd_xgf"]
            self.xg_covered_gf += gf
            self.xg_covered_ga += ga
        self.last_game_date = game_date


FEATURE_COLUMNS = [
    # Home team point-in-time
    "home_gp", "home_win_pct", "home_points_pct", "home_gf_pg", "home_ga_pg",
    "home_home_win_pct", "home_form_win_pct", "home_form_gf", "home_form_ga",
    "home_rest_days", "home_b2b", "home_streak", "home_trend",
    # Away team point-in-time
    "away_gp", "away_win_pct", "away_points_pct", "away_gf_pg", "away_ga_pg",
    "away_road_win_pct", "away_form_win_pct", "away_form_gf", "away_form_ga",
    "away_rest_days", "away_b2b", "away_streak", "away_trend",
    # MoneyPuck xG (point-in-time, see moneypuck_data.py)
    "home_xgf_per60", "home_xga_per60", "home_high_danger_xg_share",
    "home_xg_luck_for", "home_xg_luck_against",
    "away_xgf_per60", "away_xga_per60", "away_high_danger_xg_share",
    "away_xg_luck_for", "away_xg_luck_against",
    # Starting goalies (point-in-time, from actual boxscores where known)
    "home_goalie_starts", "home_goalie_sv_pct", "home_goalie_gaa", "home_goalie_recent_sv_pct",
    "away_goalie_starts", "away_goalie_sv_pct", "away_goalie_gaa", "away_goalie_recent_sv_pct",
    "goalie_sv_pct_diff", "goalie_recent_sv_pct_diff", "goalie_experience_diff",

    # Differentials + matchup
    "win_pct_diff", "points_pct_diff", "form_diff", "goal_diff_rate_diff",
    "xg_diff_rate_diff", "rest_diff", "h2h_home_win_rate", "h2h_meetings",
]

LABEL_COLUMNS = ["home_win", "total_goals", "goal_diff", "went_ot"]

META_COLUMNS = ["game_id", "season", "date", "home_team", "away_team"]

# The goalie block within FEATURE_COLUMNS — split out so model_gate.py's
# ablation and the production xG model (src/models/xg_production.py, the
# ablation winner: xG in, goalie block out) share one definition instead of
# two lists that can drift apart.
GOALIE_FEATURE_COLUMNS = [
    "home_goalie_starts", "home_goalie_sv_pct", "home_goalie_gaa", "home_goalie_recent_sv_pct",
    "away_goalie_starts", "away_goalie_sv_pct", "away_goalie_gaa", "away_goalie_recent_sv_pct",
    "goalie_sv_pct_diff", "goalie_recent_sv_pct_diff", "goalie_experience_diff",
]

XG_FEATURE_COLUMNS = [c for c in FEATURE_COLUMNS if c not in GOALIE_FEATURE_COLUMNS]


def build_point_in_time_rows(games: list, min_gp: int = 5, starters: dict = None,
                              xg_data: dict = None) -> list:
    """
    Walk games chronologically and emit one feature row per game, computed
    strictly from prior games. Team season stats reset at season boundaries;
    head-to-head history and goalie history carry across seasons (point-in-time).

    Rows where either team has fewer than min_gp games that season are
    skipped (early-season stats are mostly priors/noise).

    `starters`, if given, is {game_id: (home_starter, away_starter)} from
    fetch_all_starters() — the actual starting goalie per game, which is
    public pre-game info and therefore safe to use as a feature (only that
    game's in-game line is withheld until after the row is emitted).

    `xg_data`, if given, is {game_id: {team_abbrev: {...}}} from
    moneypuck_data.load_moneypuck_xg() — per-game team xG. For a game whose
    season is in MONEYPUCK_SEASONS, both teams MUST be present in xg_data
    (a completed season's MoneyPuck coverage should be total); a missing
    join there is treated as a data bug and raises immediately rather than
    silently dropping the xG signal for that game. Games outside
    MONEYPUCK_SEASONS (a season MoneyPuck hasn't published yet) simply get
    no xG update that game — the team's xG state falls back to the
    neutral defaults in _TeamState.snapshot() until data exists.
    """
    games = sorted(games, key=lambda g: (g["date"], g["id"]))
    starters = starters or {}
    xg_data = xg_data or {}

    team_states = {}                    # (season, team) -> _TeamState
    goalie_states = {}                  # goalie_id -> _GoalieState (career, cross-season)
    h2h_results = defaultdict(list)     # frozenset({a, b}) -> [(date, winner_abbrev)]
    rows = []

    for g in games:
        season = g["season"]
        home, away = g["home_team"], g["away_team"]
        date = g["date"]

        hs = team_states.setdefault((season, home), _TeamState())
        as_ = team_states.setdefault((season, away), _TeamState())

        home_starter, away_starter = starters.get(g["id"], (None, None))
        home_gs = (goalie_states.setdefault(home_starter["id"], _GoalieState())
                   if home_starter else None)
        away_gs = (goalie_states.setdefault(away_starter["id"], _GoalieState())
                   if away_starter else None)

        home_xg = away_xg = None
        if season in MONEYPUCK_SEASONS:
            game_xg = xg_data.get(g["id"])
            if game_xg is None or home not in game_xg or away not in game_xg:
                raise ValueError(
                    f"MoneyPuck xG data missing for game {g['id']} "
                    f"({date}, {away} @ {home}, season {season}) — season is "
                    f"in MONEYPUCK_SEASONS so coverage should be total. "
                    f"Refusing to silently drop xG signal for this game."
                )
            home_xg, away_xg = game_xg[home], game_xg[away]

        if hs.gp >= min_gp and as_.gp >= min_gp:
            h = hs.snapshot(date)
            a = as_.snapshot(date)
            hg = home_gs.snapshot() if home_gs else _DEFAULT_GOALIE_SNAPSHOT
            ag = away_gs.snapshot() if away_gs else _DEFAULT_GOALIE_SNAPSHOT

            pair = frozenset((home, away))
            prior = h2h_results[pair][-10:]
            h2h_rate = (sum(1 for _, w in prior if w == home) / len(prior)) if prior else 0.5

            row = {
                "game_id": g["id"], "season": season, "date": date,
                "home_team": home, "away_team": away,

                "home_gp": h["gp"], "home_win_pct": h["win_pct"],
                "home_points_pct": h["points_pct"],
                "home_gf_pg": h["gf_pg"], "home_ga_pg": h["ga_pg"],
                "home_home_win_pct": h["home_win_pct"],
                "home_form_win_pct": h["form_win_pct"],
                "home_form_gf": h["form_gf"], "home_form_ga": h["form_ga"],
                "home_rest_days": h["rest_days"], "home_b2b": h["b2b"],
                "home_streak": h["streak"], "home_trend": h["trend"],

                "away_gp": a["gp"], "away_win_pct": a["win_pct"],
                "away_points_pct": a["points_pct"],
                "away_gf_pg": a["gf_pg"], "away_ga_pg": a["ga_pg"],
                "away_road_win_pct": a["road_win_pct"],
                "away_form_win_pct": a["form_win_pct"],
                "away_form_gf": a["form_gf"], "away_form_ga": a["form_ga"],
                "away_rest_days": a["rest_days"], "away_b2b": a["b2b"],
                "away_streak": a["streak"], "away_trend": a["trend"],

                "home_xgf_per60": h["xgf_per60"], "home_xga_per60": h["xga_per60"],
                "home_high_danger_xg_share": h["high_danger_xg_share"],
                "home_xg_luck_for": h["xg_luck_for"],
                "home_xg_luck_against": h["xg_luck_against"],
                "away_xgf_per60": a["xgf_per60"], "away_xga_per60": a["xga_per60"],
                "away_high_danger_xg_share": a["high_danger_xg_share"],
                "away_xg_luck_for": a["xg_luck_for"],
                "away_xg_luck_against": a["xg_luck_against"],

                "home_goalie_starts": hg["starts"],
                "home_goalie_sv_pct": hg["sv_pct"],
                "home_goalie_gaa": hg["gaa"],
                "home_goalie_recent_sv_pct": hg["recent_sv_pct"],
                "away_goalie_starts": ag["starts"],
                "away_goalie_sv_pct": ag["sv_pct"],
                "away_goalie_gaa": ag["gaa"],
                "away_goalie_recent_sv_pct": ag["recent_sv_pct"],
                "goalie_sv_pct_diff": hg["sv_pct"] - ag["sv_pct"],
                "goalie_recent_sv_pct_diff": hg["recent_sv_pct"] - ag["recent_sv_pct"],
                "goalie_experience_diff": (min(hg["starts"], 60) - min(ag["starts"], 60)),

                "win_pct_diff": h["win_pct"] - a["win_pct"],
                "points_pct_diff": h["points_pct"] - a["points_pct"],
                "form_diff": h["form_win_pct"] - a["form_win_pct"],
                "goal_diff_rate_diff": (h["gf_pg"] - h["ga_pg"]) - (a["gf_pg"] - a["ga_pg"]),
                "xg_diff_rate_diff": ((h["xgf_per60"] - h["xga_per60"])
                                      - (a["xgf_per60"] - a["xga_per60"])),
                "rest_diff": h["rest_days"] - a["rest_days"],
                "h2h_home_win_rate": h2h_rate,
                "h2h_meetings": len(prior),

                "home_win": 1 if g["home_win"] else 0,
                "total_goals": g["total_goals"],
                "goal_diff": g["goal_diff"],
                "went_ot": 0 if g["last_period_type"] == "REG" else 1,
            }
            rows.append(row)

        # Update state AFTER emitting the row (point-in-time guarantee)
        lost_in_extra = g["last_period_type"] in ("OT", "SO")
        hs.record(date, g["home_win"], g["home_score"], g["away_score"],
                  is_home=True, lost_in_extra=(not g["home_win"]) and lost_in_extra,
                  xg=home_xg)
        as_.record(date, not g["home_win"], g["away_score"], g["home_score"],
                   is_home=False, lost_in_extra=g["home_win"] and lost_in_extra,
                   xg=away_xg)
        h2h_results[frozenset((home, away))].append(
            (date, home if g["home_win"] else away))
        if home_gs is not None:
            home_gs.record(home_starter["shots_against"], home_starter["saves"],
                            home_starter["goals_against"], home_starter["minutes"])
        if away_gs is not None:
            away_gs.record(away_starter["shots_against"], away_starter["saves"],
                            away_starter["goals_against"], away_starter["minutes"])

    return rows


def build_live_state(games: list, xg_data: dict = None) -> tuple:
    """
    Serving-time counterpart to build_point_in_time_rows(): replay every game
    in `games` chronologically and return the resulting point-in-time state,
    for predicting a game that hasn't been played yet — no rows are emitted
    and no min_gp filtering happens (state must reflect every game played,
    even a team's first few).

    Unlike build_point_in_time_rows() — where a season in MONEYPUCK_SEASONS
    must have total xG coverage, and a missing join is a hard error — a
    missing per-game xG join here is NOT an error. MoneyPuck publishes with a
    delay, so the current season's most recent games may not be covered yet.
    A missing join simply means that game contributes no xG update; each
    team's xG state carries forward from its last covered game rather than
    resetting to the neutral default (see _TeamState.snapshot()), so the
    in-season lag never silently looks like "no signal".

    Returns (team_states, h2h_results):
      team_states: {(season, team_abbrev): _TeamState} — pass to
        snapshot_team_state() rather than touching _TeamState directly.
      h2h_results: {frozenset({a, b}): [(date, winner_abbrev), ...]}
    """
    games = sorted(games, key=lambda g: (g["date"], g["id"]))
    xg_data = xg_data or {}

    team_states = {}
    h2h_results = defaultdict(list)

    for g in games:
        season = g["season"]
        home, away = g["home_team"], g["away_team"]
        date = g["date"]

        hs = team_states.setdefault((season, home), _TeamState())
        as_ = team_states.setdefault((season, away), _TeamState())

        game_xg = xg_data.get(g["id"])
        home_xg = game_xg.get(home) if game_xg else None
        away_xg = game_xg.get(away) if game_xg else None

        lost_in_extra = g["last_period_type"] in ("OT", "SO")
        hs.record(date, g["home_win"], g["home_score"], g["away_score"],
                  is_home=True, lost_in_extra=(not g["home_win"]) and lost_in_extra,
                  xg=home_xg)
        as_.record(date, not g["home_win"], g["away_score"], g["home_score"],
                   is_home=False, lost_in_extra=g["home_win"] and lost_in_extra,
                   xg=away_xg)
        h2h_results[frozenset((home, away))].append(
            (date, home if g["home_win"] else away))

    return team_states, h2h_results


def snapshot_team_state(team_states: dict, season: str, team: str, as_of_date: str) -> dict:
    """Public accessor for a team's point-in-time snapshot out of the
    (season, team) -> _TeamState mapping returned by build_live_state(), using
    the identical _TeamState.snapshot() logic training rows are built from.
    A team with no state yet this season (hasn't played, or a new season with
    no games) gets the same neutral-prior snapshot an early training row would."""
    state = team_states.get((season, team))
    return (state or _TeamState()).snapshot(as_of_date)


def write_csv(rows: list, out_path: str):
    """Write dataset rows to CSV."""
    columns = META_COLUMNS + FEATURE_COLUMNS + LABEL_COLUMNS
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def build_training_set(seasons: list, min_gp: int = 5,
                       out_path: str = None, verbose: bool = True,
                       with_goalies: bool = True, with_xg: bool = True) -> list:
    """Fetch all seasons, build point-in-time rows, optionally write CSV."""
    all_games = []
    for season in seasons:
        if verbose:
            print(f"Fetching {season}...")
        all_games.extend(fetch_season_games_full(season, verbose=verbose))

    starters = None
    if with_goalies:
        if verbose:
            print(f"Fetching starting goalies for {len(all_games)} games "
                  f"(one boxscore request per game, cached)...")
        starters = fetch_all_starters(all_games, verbose=verbose)

    xg_data = None
    if with_xg:
        mp_seasons = sorted(set(seasons) & MONEYPUCK_SEASONS)
        if mp_seasons:
            if verbose:
                print(f"Fetching MoneyPuck xG data for {', '.join(mp_seasons)}...")
            xg_data = load_moneypuck_xg(mp_seasons)

    rows = build_point_in_time_rows(all_games, min_gp=min_gp, starters=starters,
                                     xg_data=xg_data)
    if verbose:
        print(f"\n✓ Built {len(rows)} training rows from {len(all_games)} games "
              f"({len(all_games) - len(rows)} skipped: teams under {min_gp} GP)")

    if out_path:
        write_csv(rows, out_path)
        if verbose:
            print(f"✓ Wrote {out_path}")
    return rows
