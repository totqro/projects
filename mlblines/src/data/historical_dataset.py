"""
Point-in-time MLB dataset
=========================
The rebuilt MLB model's only source of features. Every value for a game is
computed from information that existed before first pitch:

  * team Elo, walked game by game across seasons (1/3 reversion each spring)
  * season-to-date run differential per game, shrunk toward 0
  * the PROBABLE starter's K%, BB+HBP%, HR% and outs per start, built only
    from that pitcher's game logs dated before the game (current season at
    full weight, prior season at PRIOR_SEASON_WEIGHT), each rate shrunk toward
    a replacement-level prior by batters faced
  * bullpen runs allowed per out, season to date, shrunk toward league average
  * park run factor from the three prior completed seasons, keyed by venue

The same `StateReplayer` produces training rows (snapshot every game on a date,
then apply that date's results) and live serving features (apply every
completed game, then snapshot today's slate). One code path for both, so the
model is served exactly the features it was trained on.

Why probable pitchers: the schedule's `probablePitcher` is what is announced
before the game. On a 40-game 2025 sample it matched the actual boxscore
starter in 39 games, so training on it is both pre-game and accurate.

What is deliberately NOT here: rest days and back-to-backs (MLB teams play
nearly every day, so it carries no signal), current-season standings stamped
onto old games, and any stat a pitcher accumulated after the game in question.

Data: MLB Stats API (statsapi.mlb.com), no key. A completed season is cached
for good; the current season refreshes every few hours.
"""

import bisect
import csv
import json
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import requests

from .mlb_data import TEAM_ABBREV_MAP

STATS_API = "https://statsapi.mlb.com/api/v1"
CACHE_DIR = Path(__file__).resolve().parents[2] / "cache"
CACHE_DIR.mkdir(exist_ok=True)

# 2020 (60 games) is skipped. 2021 is replayed only as burn-in for Elo and as
# the prior season for 2022 starters; training rows start in 2022.
BURN_IN_SEASON = 2021
FIRST_ROW_SEASON = 2022

# --- Elo -------------------------------------------------------------------
INITIAL_ELO = 1500.0
ELO_K = 4.0                 # MLB games are close to coin flips; small K
ELO_SEASON_REVERSION = 1.0 / 3.0

# --- Starter shrinkage -------------------------------------------------------
# Priors sit a little below league average on purpose: a pitcher with no
# track record is usually a call-up or a spot starter, not an average arm.
PRIOR_K_RATE = 0.205
PRIOR_BB_RATE = 0.095       # walks + hit batters, per batter faced
PRIOR_HR_RATE = 0.033
PRIOR_OUTS_PER_START = 15.0
# Pseudo batters faced. K% stabilises fastest, HR% slowest.
PSEUDO_BF_K = 150.0
PSEUDO_BF_BB = 300.0
PSEUDO_BF_HR = 900.0
PSEUDO_STARTS = 5.0
PRIOR_SEASON_WEIGHT = 0.6
BATTERS_PER_INNING = 4.28
FIP_CONSTANT = 3.2

# --- Team shrinkage ----------------------------------------------------------
PSEUDO_GAMES_RUN_DIFF = 25.0
LEAGUE_BULLPEN_RUNS_PER_OUT = 0.155   # ~4.2 runs per 9 innings
PSEUDO_BULLPEN_OUTS = 300.0
LEAGUE_RUNS_PER_TEAM_GAME = 4.45
PSEUDO_GAMES_RUNS = 25.0
PARK_PSEUDO_GAMES = 150.0

# Feature columns, in the order the models consume them. Every "_diff" is
# oriented so a positive value favours the HOME team.
WIN_FEATURE_COLUMNS = [
    "elo_diff",
    "sp_fip_diff",            # away starter FIP-like minus home starter's
    "sp_k_bb_diff",           # home starter K-BB% minus away starter's
    "sp_depth_diff",          # home starter outs/start minus away's
    "bullpen_diff",           # away bullpen runs/out minus home's
    "run_diff_pg_diff",       # home shrunk run diff/game minus away's
]
ELO_FEATURE_COLUMNS = ["elo_diff"]

TOTALS_FEATURE_COLUMNS = [
    "sp_fip_sum",
    "sp_depth_sum",
    "bullpen_sum",
    "home_rs_pg", "home_ra_pg", "away_rs_pg", "away_ra_pg",
    "park_factor",
    "league_rpg",
]

ID_COLUMNS = ["season", "date", "game_id", "home_team", "away_team",
              "home_sp_id", "away_sp_id", "venue_id"]
LABEL_COLUMNS = ["home_win", "home_score", "away_score", "total_runs"]
DETAIL_COLUMNS = ["home_elo", "away_elo", "home_sp_fip", "away_sp_fip",
                  "home_sp_k_bb", "away_sp_k_bb", "home_sp_bf", "away_sp_bf",
                  "home_bullpen_rpo", "away_bullpen_rpo"]
ALL_COLUMNS = (ID_COLUMNS + WIN_FEATURE_COLUMNS
               + [c for c in TOTALS_FEATURE_COLUMNS if c not in WIN_FEATURE_COLUMNS]
               + DETAIL_COLUMNS + LABEL_COLUMNS)

PLAYED_STATES = {"Final", "Completed Early"}

_session = requests.Session()


def team_abbrev(team_id) -> str:
    return TEAM_ABBREV_MAP.get(team_id, str(team_id))


# --------------------------------------------------------------------------- #
# Fetching                                                                     #
# --------------------------------------------------------------------------- #
def _get_json(url: str, params: dict, cache_name: str, ttl_hours: float) -> dict:
    cache_file = CACHE_DIR / f"{cache_name}.json"
    if cache_file.exists():
        age_hours = (time.time() - cache_file.stat().st_mtime) / 3600
        if age_hours < ttl_hours:
            return json.loads(cache_file.read_text())

    last_err = None
    for attempt in range(4):
        try:
            resp = _session.get(url, params=params, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            cache_file.write_text(json.dumps(data))
            return data
        except (requests.RequestException, ValueError) as e:
            last_err = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"MLB Stats API request failed for {cache_name}: {last_err}")


def _season_ttl_hours(season: int) -> float:
    return 24 * 365 * 10 if season < datetime.now().year else 4


SCHEDULE_FIELDS = ("dates,date,games,gamePk,officialDate,gameDate,status,detailedState,"
                   "teams,home,away,team,id,score,probablePitcher,fullName,venue,"
                   "linescore,currentInning,isTopInning,gameNumber,doubleHeader")


def fetch_season_schedule(season: int) -> list:
    """Every regular-season game in `season`, played or not, as flat dicts."""
    data = _get_json(
        f"{STATS_API}/schedule",
        {"sportId": 1, "season": season, "gameType": "R",
         "hydrate": "probablePitcher,linescore", "fields": SCHEDULE_FIELDS},
        f"hist_schedule_{season}",
        _season_ttl_hours(season),
    )
    games, seen = [], set()
    for d in data.get("dates", []):
        for g in d.get("games", []):
            pk = g.get("gamePk")
            state = g.get("status", {}).get("detailedState", "")
            # A postponed game appears twice (original date + makeup). Keep
            # only the entry that was actually played, or the scheduled one.
            if pk in seen and state not in PLAYED_STATES:
                continue
            home, away = g["teams"]["home"], g["teams"]["away"]
            ls = g.get("linescore", {}) or {}
            row = {
                "game_id": pk,
                "season": season,
                "date": g.get("officialDate") or d.get("date"),
                "game_datetime": g.get("gameDate", ""),
                "state": state,
                "home_team": team_abbrev(home["team"]["id"]),
                "away_team": team_abbrev(away["team"]["id"]),
                "home_score": home.get("score"),
                "away_score": away.get("score"),
                "home_sp_id": (home.get("probablePitcher") or {}).get("id"),
                "away_sp_id": (away.get("probablePitcher") or {}).get("id"),
                "home_sp_name": (home.get("probablePitcher") or {}).get("fullName", "TBD"),
                "away_sp_name": (away.get("probablePitcher") or {}).get("fullName", "TBD"),
                "venue_id": (g.get("venue") or {}).get("id"),
                "innings": ls.get("currentInning"),
                "ended_top": ls.get("isTopInning"),
                "game_number": g.get("gameNumber", 1),
            }
            if pk in seen:
                games = [x for x in games if x["game_id"] != pk]
            seen.add(pk)
            games.append(row)
    return games


def completed_games(games: list) -> list:
    out = []
    for g in games:
        if g["state"] not in PLAYED_STATES:
            continue
        if g["home_score"] is None or g["away_score"] is None:
            continue
        if g["home_score"] == g["away_score"]:
            continue  # suspended ties never resolved; no winner to learn from
        out.append(g)
    return out


LOG_FIELDS = ("people,id,fullName,pitchHand,code,stats,splits,date,game,gamePk,stat,"
              "battersFaced,strikeOuts,baseOnBalls,hitByPitch,homeRuns,outs,runs,gamesStarted")


def fetch_pitcher_logs(pitcher_ids, season: int, batch_size: int = 40) -> dict:
    """{pitcher_id: [log dicts sorted by date]} for one season. One request per
    batch, cached by season and batch contents."""
    ids = sorted({int(p) for p in pitcher_ids if p})
    out = {}
    for i in range(0, len(ids), batch_size):
        chunk = ids[i:i + batch_size]
        key = f"hist_pitlogs_{season}_{chunk[0]}_{chunk[-1]}_{len(chunk)}"
        data = _get_json(
            f"{STATS_API}/people",
            {"personIds": ",".join(map(str, chunk)),
             "hydrate": f"stats(group=[pitching],type=[gameLog],season={season})",
             "fields": LOG_FIELDS},
            key, _season_ttl_hours(season),
        )
        for person in data.get("people", []):
            logs = []
            for sg in person.get("stats", []) or []:
                for s in sg.get("splits", []) or []:
                    st = s.get("stat", {})
                    logs.append({
                        "date": s.get("date"),
                        "game_id": (s.get("game") or {}).get("gamePk"),
                        "bf": int(st.get("battersFaced", 0) or 0),
                        "k": int(st.get("strikeOuts", 0) or 0),
                        "bb": int(st.get("baseOnBalls", 0) or 0) + int(st.get("hitByPitch", 0) or 0),
                        "hr": int(st.get("homeRuns", 0) or 0),
                        "outs": int(st.get("outs", 0) or 0),
                        "runs": int(st.get("runs", 0) or 0),
                        "gs": int(st.get("gamesStarted", 0) or 0),
                    })
            logs.sort(key=lambda x: (x["date"] or "", x["game_id"] or 0))
            out[person["id"]] = logs
    return out


def fetch_pitcher_names(pitcher_ids) -> dict:
    ids = sorted({int(p) for p in pitcher_ids if p})
    names = {}
    for i in range(0, len(ids), 100):
        chunk = ids[i:i + 100]
        data = _get_json(f"{STATS_API}/people",
                         {"personIds": ",".join(map(str, chunk)),
                          "fields": "people,id,fullName,pitchHand,code"},
                         f"hist_people_{chunk[0]}_{chunk[-1]}_{len(chunk)}", 24 * 30)
        for p in data.get("people", []):
            names[p["id"]] = {"name": p.get("fullName", "Unknown"),
                              "hand": (p.get("pitchHand") or {}).get("code", "R")}
    return names


# --------------------------------------------------------------------------- #
# Pitcher index: point-in-time cumulative sums                                #
# --------------------------------------------------------------------------- #
class PitcherIndex:
    """Prefix sums of each pitcher's logs per season so 'everything before
    date D' is a binary search, not a scan."""

    STAT_KEYS = ("bf", "k", "bb", "hr", "outs", "starts", "start_outs")

    def __init__(self):
        self._data = {}           # (pid, season) -> (dates, prefix rows)
        self._by_game = {}        # (pid, game_id) -> log

    def add_season(self, season: int, logs_by_pitcher: dict):
        for pid, logs in logs_by_pitcher.items():
            dates, prefix = [], []
            run = dict.fromkeys(self.STAT_KEYS, 0)
            for lg in logs:
                if not lg["date"]:
                    continue
                run["bf"] += lg["bf"]
                run["k"] += lg["k"]
                run["bb"] += lg["bb"]
                run["hr"] += lg["hr"]
                run["outs"] += lg["outs"]
                if lg["gs"]:
                    run["starts"] += 1
                    run["start_outs"] += lg["outs"]
                dates.append(lg["date"])
                prefix.append(dict(run))
                if lg["game_id"]:
                    self._by_game[(pid, lg["game_id"])] = lg
            self._data[(pid, season)] = (dates, prefix)

    def totals_before(self, pid, season: int, date: str) -> dict:
        zero = dict.fromkeys(self.STAT_KEYS, 0)
        entry = self._data.get((pid, season))
        if not entry:
            return zero
        dates, prefix = entry
        i = bisect.bisect_left(dates, date)
        return prefix[i - 1] if i > 0 else zero

    def season_totals(self, pid, season: int) -> dict:
        entry = self._data.get((pid, season))
        if not entry or not entry[1]:
            return dict.fromkeys(self.STAT_KEYS, 0)
        return entry[1][-1]

    def game_line(self, pid, game_id):
        return self._by_game.get((pid, game_id))


def starter_profile(index: PitcherIndex, pid, season: int, date: str) -> dict:
    """Shrunk pre-game rates for a probable starter."""
    cur = index.totals_before(pid, season, date) if pid else dict.fromkeys(PitcherIndex.STAT_KEYS, 0)
    prev = index.season_totals(pid, season - 1) if pid else dict.fromkeys(PitcherIndex.STAT_KEYS, 0)
    w = PRIOR_SEASON_WEIGHT

    def comb(key):
        return cur[key] + w * prev[key]

    bf = comb("bf")
    k_rate = (comb("k") + PSEUDO_BF_K * PRIOR_K_RATE) / (bf + PSEUDO_BF_K)
    bb_rate = (comb("bb") + PSEUDO_BF_BB * PRIOR_BB_RATE) / (bf + PSEUDO_BF_BB)
    hr_rate = (comb("hr") + PSEUDO_BF_HR * PRIOR_HR_RATE) / (bf + PSEUDO_BF_HR)
    starts = comb("starts")
    depth = (comb("start_outs") + PSEUDO_STARTS * PRIOR_OUTS_PER_START) / (starts + PSEUDO_STARTS)

    # FIP = (13*HR + 3*(BB+HBP) - 2*K) / IP + constant. The rates here are per
    # batter faced, so scale by a league-typical 4.28 batters per inning. The
    # level lands on the ERA scale; only differences and sums enter the models.
    fip = (13 * hr_rate + 3 * bb_rate - 2 * k_rate) * BATTERS_PER_INNING + FIP_CONSTANT
    return {
        "fip": fip,
        "k_bb": k_rate - bb_rate,
        "depth": depth,
        "bf": bf,
        "k_rate": k_rate,
        "bb_rate": bb_rate,
        "hr_rate": hr_rate,
    }


# --------------------------------------------------------------------------- #
# Team / league state replay                                                   #
# --------------------------------------------------------------------------- #
class StateReplayer:
    """Walks completed games in order. `features()` reads state; `apply()`
    writes it. Training calls features() for a whole date before apply()ing
    that date, so no game ever sees its own result or a same-day result."""

    def __init__(self, pitcher_index: PitcherIndex):
        self.pitchers = pitcher_index
        self.elo = {}
        self.elo_season = {}
        self.season = None
        self.team = defaultdict(lambda: {"g": 0, "rs": 0, "ra": 0,
                                         "bp_runs": 0.0, "bp_outs": 0.0})
        self.league_runs = 0
        self.league_team_games = 0
        # Park factor inputs, per completed season: venue -> [runs, games] at
        # the venue, and team -> [runs, games] in that team's road games.
        self.park_by_season = defaultdict(lambda: {"venue": defaultdict(lambda: [0, 0]),
                                                    "venue_team": defaultdict(lambda: defaultdict(int)),
                                                    "road": defaultdict(lambda: [0, 0])})

    # -- season handling ------------------------------------------------------
    def _roll_season(self, season: int):
        if self.season == season:
            return
        self.season = season
        self.team.clear()
        self.league_runs = 0
        self.league_team_games = 0

    def _elo_for(self, team: str, season: int) -> float:
        if team not in self.elo:
            self.elo[team] = INITIAL_ELO
            self.elo_season[team] = season
        elif self.elo_season[team] != season:
            self.elo[team] += (INITIAL_ELO - self.elo[team]) * ELO_SEASON_REVERSION
            self.elo_season[team] = season
        return self.elo[team]

    # -- reads ------------------------------------------------------------------
    def _team_rates(self, team: str) -> dict:
        t = self.team[team]
        g = t["g"]
        run_diff_pg = (t["rs"] - t["ra"]) / (g + PSEUDO_GAMES_RUN_DIFF)
        rs_pg = (t["rs"] + PSEUDO_GAMES_RUNS * LEAGUE_RUNS_PER_TEAM_GAME) / (g + PSEUDO_GAMES_RUNS)
        ra_pg = (t["ra"] + PSEUDO_GAMES_RUNS * LEAGUE_RUNS_PER_TEAM_GAME) / (g + PSEUDO_GAMES_RUNS)
        bullpen = ((t["bp_runs"] + PSEUDO_BULLPEN_OUTS * LEAGUE_BULLPEN_RUNS_PER_OUT)
                   / (t["bp_outs"] + PSEUDO_BULLPEN_OUTS))
        return {"gp": g, "run_diff_pg": run_diff_pg, "rs_pg": rs_pg, "ra_pg": ra_pg,
                "bullpen_rpo": bullpen}

    def park_factor(self, venue_id, home_team: str, season: int) -> float:
        """Runs per game at this venue vs. its home team's road games, over the
        three prior completed seasons, shrunk toward 1.0."""
        venue_runs = venue_games = road_runs = road_games = 0
        for s in (season - 1, season - 2, season - 3):
            p = self.park_by_season.get(s)
            if not p:
                continue
            games_here = p["venue_team"][venue_id].get(home_team, 0)
            if not games_here:
                continue
            vr, vg = p["venue"][(venue_id, home_team)]
            rr, rg = p["road"][home_team]
            venue_runs += vr
            venue_games += vg
            road_runs += rr
            road_games += rg
        if not venue_games or not road_games:
            return 1.0
        raw = (venue_runs / venue_games) / (road_runs / road_games)
        n = min(venue_games, road_games)
        return (raw * n + PARK_PSEUDO_GAMES) / (n + PARK_PSEUDO_GAMES)

    def features(self, game: dict) -> dict:
        season, date = game["season"], game["date"]
        self._roll_season(season)
        home, away = game["home_team"], game["away_team"]
        h_elo = self._elo_for(home, season)
        a_elo = self._elo_for(away, season)
        hsp = starter_profile(self.pitchers, game.get("home_sp_id"), season, date)
        asp = starter_profile(self.pitchers, game.get("away_sp_id"), season, date)
        ht, at = self._team_rates(home), self._team_rates(away)
        # Runs per game (both teams), season to date, shrunk over 50 games.
        league_rpg = ((self.league_runs + 50 * 2 * LEAGUE_RUNS_PER_TEAM_GAME)
                      / (self.league_team_games / 2 + 50))

        return {
            "elo_diff": h_elo - a_elo,
            "sp_fip_diff": asp["fip"] - hsp["fip"],
            "sp_k_bb_diff": hsp["k_bb"] - asp["k_bb"],
            "sp_depth_diff": hsp["depth"] - asp["depth"],
            "bullpen_diff": at["bullpen_rpo"] - ht["bullpen_rpo"],
            "run_diff_pg_diff": ht["run_diff_pg"] - at["run_diff_pg"],

            "sp_fip_sum": hsp["fip"] + asp["fip"],
            "sp_depth_sum": hsp["depth"] + asp["depth"],
            "bullpen_sum": ht["bullpen_rpo"] + at["bullpen_rpo"],
            "home_rs_pg": ht["rs_pg"], "home_ra_pg": ht["ra_pg"],
            "away_rs_pg": at["rs_pg"], "away_ra_pg": at["ra_pg"],
            "park_factor": self.park_factor(game.get("venue_id"), home, season),
            "league_rpg": league_rpg,

            "home_elo": h_elo, "away_elo": a_elo,
            "home_sp_fip": hsp["fip"], "away_sp_fip": asp["fip"],
            "home_sp_k_bb": hsp["k_bb"], "away_sp_k_bb": asp["k_bb"],
            "home_sp_bf": hsp["bf"], "away_sp_bf": asp["bf"],
            "home_bullpen_rpo": ht["bullpen_rpo"], "away_bullpen_rpo": at["bullpen_rpo"],
        }

    # -- writes -----------------------------------------------------------------
    def _bullpen_line(self, team_side: str, game: dict):
        """(bullpen runs, bullpen outs) for one side, or None if the probable
        starter's log for this game isn't found (he didn't actually start)."""
        sp = game.get(f"{team_side}_sp_id")
        line = self.pitchers.game_line(sp, game["game_id"]) if sp else None
        if not line or not line["gs"]:
            return None
        runs_allowed = game["away_score"] if team_side == "home" else game["home_score"]
        innings = game.get("innings") or 9
        if team_side == "home":
            team_outs = 3 * innings
        else:
            team_outs = 3 * (innings - 1) if game.get("ended_top") else 3 * innings
        bp_outs = max(team_outs - line["outs"], 0)
        bp_runs = max(runs_allowed - line["runs"], 0)
        return bp_runs, bp_outs

    def apply(self, game: dict):
        season = game["season"]
        self._roll_season(season)
        home, away = game["home_team"], game["away_team"]
        hs, as_ = game["home_score"], game["away_score"]

        h_elo, a_elo = self._elo_for(home, season), self._elo_for(away, season)
        expected = 1.0 / (1.0 + 10 ** (-(h_elo - a_elo) / 400.0))
        delta = ELO_K * ((1.0 if hs > as_ else 0.0) - expected)
        self.elo[home] = h_elo + delta
        self.elo[away] = a_elo - delta

        for side, team, rs, ra in (("home", home, hs, as_), ("away", away, as_, hs)):
            t = self.team[team]
            t["g"] += 1
            t["rs"] += rs
            t["ra"] += ra
            bp = self._bullpen_line(side, game)
            if bp:
                t["bp_runs"] += bp[0]
                t["bp_outs"] += bp[1]
        self.league_runs += hs + as_
        self.league_team_games += 2

        p = self.park_by_season[season]
        venue = game.get("venue_id")
        p["venue"][(venue, home)][0] += hs + as_
        p["venue"][(venue, home)][1] += 1
        p["venue_team"][venue][home] += 1
        p["road"][away][0] += hs + as_
        p["road"][away][1] += 1


# --------------------------------------------------------------------------- #
# Building                                                                     #
# --------------------------------------------------------------------------- #
def seasons_through_current() -> list:
    now = datetime.now()
    last = now.year if now.month >= 3 else now.year - 1
    return [s for s in range(BURN_IN_SEASON, last + 1) if s != 2020]


def load_history(seasons: list = None, verbose: bool = True) -> tuple:
    """Fetch schedules and pitcher logs for `seasons`. Returns
    (schedules_by_season, PitcherIndex)."""
    seasons = seasons or seasons_through_current()
    schedules = {}
    for s in seasons:
        if verbose:
            print(f"  schedule {s}...", flush=True)
        schedules[s] = fetch_season_schedule(s)

    index = PitcherIndex()
    for s in seasons:
        # Logs for season s are needed for s's own games and as the prior
        # season for s+1's starters.
        ids = set()
        for yr in (s, s + 1):
            for g in schedules.get(yr, []):
                ids.add(g["home_sp_id"])
                ids.add(g["away_sp_id"])
        ids.discard(None)
        if verbose:
            print(f"  pitcher logs {s}: {len(ids)} pitchers...", flush=True)
        index.add_season(s, fetch_pitcher_logs(ids, s))
    return schedules, index


def build_rows(schedules: dict, index: PitcherIndex, first_row_season: int = FIRST_ROW_SEASON,
               before_date: str = None) -> tuple:
    """Replay every completed game in order. Returns (rows, replayer) where the
    replayer holds post-last-game state, ready to serve upcoming games.

    `before_date` (YYYY-MM-DD) stops the replay at games dated before it. The
    daily run passes today's date so an early game that already finished can't
    leak into a later game's features, which training never allows either."""
    games = []
    for s in sorted(schedules):
        games.extend(g for g in completed_games(schedules[s])
                     if before_date is None or g["date"] < before_date)
    games.sort(key=lambda g: (g["date"], g["game_datetime"], g["game_id"]))

    replayer = StateReplayer(index)
    rows = []
    i = 0
    while i < len(games):
        date = games[i]["date"]
        j = i
        while j < len(games) and games[j]["date"] == date:
            j += 1
        day = games[i:j]
        snaps = [replayer.features(g) for g in day]
        for g, f in zip(day, snaps):
            if g["season"] < first_row_season:
                continue
            rows.append({
                "season": g["season"], "date": g["date"], "game_id": g["game_id"],
                "home_team": g["home_team"], "away_team": g["away_team"],
                "home_sp_id": g["home_sp_id"] or "", "away_sp_id": g["away_sp_id"] or "",
                "venue_id": g["venue_id"] or "",
                **f,
                "home_win": int(g["home_score"] > g["away_score"]),
                "home_score": g["home_score"], "away_score": g["away_score"],
                "total_runs": g["home_score"] + g["away_score"],
            })
        for g in day:
            replayer.apply(g)
        i = j
    return rows, replayer


def write_csv(rows: list, path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ALL_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in ALL_COLUMNS})


def load_csv(path) -> list:
    numeric_int = {"season", "home_win", "home_score", "away_score", "total_runs"}
    with open(path) as f:
        rows = []
        for r in csv.DictReader(f):
            for c in WIN_FEATURE_COLUMNS + TOTALS_FEATURE_COLUMNS + DETAIL_COLUMNS:
                r[c] = float(r[c])
            for c in numeric_int:
                r[c] = int(r[c])
            rows.append(r)
    return rows
