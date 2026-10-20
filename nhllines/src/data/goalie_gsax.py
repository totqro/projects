"""
Goalie GSAx (goals saved above expected) ratings, point-in-time.
================================================================
Save percentage mostly measures the team in front of a goalie. GSAx measures
the goalie against the quality of the shots he actually faced:

    GSAx = expected goals on the shots on goal he faced  -  goals he allowed

Source: the MoneyPuck shots files already cached for the xG features
(moneypuck_data.py). Per shot: `goalieIdForShot`, `goal`, `xGoal` (P(goal) for
the ATTEMPT, so it includes the chance the shot misses the net) and
`xShotWasOnGoal`. A goalie only ever faces shots on goal, so the right
expectation for one he faced is xGoal / xShotWasOnGoal = P(goal | on goal).
Empty-net shots (goalie id 0) belong to nobody and are dropped.

That conditional form still sums ~10% under actual goals league-wide, which
would make the average goalie look like a -GSAx goalie. It is rescaled by one
fixed factor (goals / xG) fitted on the 2018-2021 seasons only — before any
season the model is trained or tested on — so a league-average goalie sits at
zero and no test-season information enters the scale.

Ratings are point-in-time and belong to the PLAYER, not the team:

    rating = (decayed GSAx sum) / (decayed shots faced + PRIOR_SHOTS)

PRIOR_SHOTS shrinks toward zero (a rookie is league average; one hot month is
not elite). SEASON_CARRY decays the sums at every season boundary, so an old
season counts for less. Units are goals per game (x AVG_SHOTS_ON_GOAL_PER_GAME).

PRIOR_SHOTS and SEASON_CARRY are fixed a priori, not tuned on the gate's
held-out season; goalie_gate.py prints a sensitivity table for information
only.
"""

import csv
import json
from collections import defaultdict, deque
from pathlib import Path

from .moneypuck_data import download_season_shots, _current_season_start_year
from .nhl_data import CACHE_DIR

CALIBRATION_YEARS = (2018, 2019, 2020, 2021)

PRIOR_SHOTS = 600.0        # ~20-22 games of shots on goal
SEASON_CARRY = 0.7         # fraction of last season's evidence kept
AVG_SHOTS_ON_GOAL_PER_GAME = 28.0
EXPECTED_STARTER_WINDOW = 10


def _cache_path(year: int) -> Path:
    return CACHE_DIR / f"goalie_gsax_{year}.json"


def aggregate_season_goalie_games(year: int) -> dict:
    """{nhl_game_id: {goalie_id: {"x": cond-xG faced, "g": goals allowed,
    "n": shots on goal faced}}} for one season's regular-season games.

    A completed season is cached to JSON forever (parsing the 65MB shots file
    takes seconds; the result never changes). The in-progress season is
    re-parsed from the shots file, which download_season_shots() refreshes."""
    completed = year < _current_season_start_year()
    path = _cache_path(year)
    if completed and path.exists():
        raw = json.loads(path.read_text())
        return {int(gid): {int(p): v for p, v in goalies.items()}
                for gid, goalies in raw.items()}

    games = defaultdict(dict)
    with open(download_season_shots(year), newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("isPlayoffGame") != "0":
                continue
            if float(row.get("shotWasOnGoal") or 0) != 1:
                continue
            goalie = int(float(row.get("goalieIdForShot") or 0))
            if not goalie:          # empty net
                continue
            x_on = float(row.get("xShotWasOnGoal") or 0)
            x = min(1.0, float(row.get("xGoal") or 0) / x_on) if x_on > 0 else 0.0
            gid = year * 1_000_000 + int(row["game_id"])
            line = games[gid].setdefault(goalie, {"x": 0.0, "g": 0, "n": 0})
            line["x"] += x
            line["g"] += int(float(row.get("goal") or 0))
            line["n"] += 1

    games = dict(games)
    if completed:
        path.write_text(json.dumps(games))
    return games


def load_goalie_games(years: list) -> dict:
    merged = {}
    for year in years:
        merged.update(aggregate_season_goalie_games(year))
    return merged


def calibration_factor(games_by_year: dict = None) -> float:
    """goals / xG over CALIBRATION_YEARS: the fixed scale that puts the
    league-average goalie at zero GSAx."""
    x = g = 0.0
    for year in CALIBRATION_YEARS:
        games = (games_by_year or {}).get(year) or aggregate_season_goalie_games(year)
        for goalies in games.values():
            for line in goalies.values():
                x += line["x"]
                g += line["g"]
    return g / x


class GoalieRatings:
    """Rolling per-goalie GSAx evidence with season decay."""

    def __init__(self, scale: float, prior_shots: float = PRIOR_SHOTS,
                 season_carry: float = SEASON_CARRY):
        self.scale = scale
        self.prior_shots = prior_shots
        self.season_carry = season_carry
        self._gsax = defaultdict(float)
        self._shots = defaultdict(float)

    def new_season(self):
        for gid in self._gsax:
            self._gsax[gid] *= self.season_carry
            self._shots[gid] *= self.season_carry

    def record(self, goalie_id: int, line: dict):
        self._gsax[goalie_id] += line["x"] * self.scale - line["g"]
        self._shots[goalie_id] += line["n"]

    def rating(self, goalie_id) -> float:
        """Expected goals saved above average per game. 0.0 for a goalie
        with no history, or when the starter is unknown."""
        if not goalie_id:
            return 0.0
        return (self._gsax[goalie_id] / (self._shots[goalie_id] + self.prior_shots)
                * AVG_SHOTS_ON_GOAL_PER_GAME)


class StarterHistory:
    """Each team's recent starters, for the expected-starter rating used when
    the real starter is not yet known."""

    def __init__(self, window: int = EXPECTED_STARTER_WINDOW):
        self.window = window
        self._recent = defaultdict(lambda: deque(maxlen=window))

    def record(self, team: str, goalie_id):
        if goalie_id:
            self._recent[team].append(goalie_id)

    def expected_rating(self, team: str, ratings: GoalieRatings) -> float:
        recent = self._recent[team]
        if not recent:
            return 0.0
        return sum(ratings.rating(g) for g in recent) / len(recent)


class StarterShare:
    """How much a goalie is his team's number one, point-in-time: his share of
    the team's last `window` starts. ~1.0 for a workhorse, ~0.2-0.4 for a
    backup, 0.0 for a goalie with no recent start for this team (an emergency
    call-up — or a newly signed starter, which is the known blind spot: the
    first few games of a new #1 read as 'backup')."""

    def __init__(self, window: int = 20, typical_window: int = 10):
        self.window = window
        self.typical_window = typical_window
        self._recent = defaultdict(lambda: deque(maxlen=window))

    def share(self, team: str, goalie_id) -> float:
        recent = self._recent[team]
        if not goalie_id or not recent:
            return 0.0
        return sum(1 for g in recent if g == goalie_id) / len(recent)

    def typical(self, team: str) -> float:
        """What is known BEFORE the starter is announced: the mean share of
        the team's last few starters — high for a team that rides one goalie,
        lower for a tandem."""
        last = list(self._recent[team])[-self.typical_window:]
        if not last:
            return 0.0
        return sum(self.share(team, g) for g in last) / len(last)

    def record(self, team: str, goalie_id):
        if goalie_id:
            self._recent[team].append(goalie_id)
