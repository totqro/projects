"""
Fallback per-game team xG from NHL API play-by-play.
=====================================================
Used at serving time for current-season games MoneyPuck hasn't published
(publishing lag, or MoneyPuck not posting the season at all). Produces the
same {nhl_game_id: {team_abbrev: {...}}} shape as
moneypuck_data.aggregate_season_game_team_xg(), so build_live_state() can't
tell the sources apart.

Each unblocked shot attempt (shot-on-goal / missed-shot / goal, matching the
MoneyPuck shots file, which excludes blocked shots) is scored with the repo's
own five-feature xG model (xgcalc/web/xg_model.json: distance, angle,
shot type, rebound, situation), with the features rebuilt from play-by-play
the same way xgcalc/src/data/clean.py builds them from MoneyPuck columns.

Caveat: that model was trained on MoneyPuck shots but is not MoneyPuck's own
xG model, which uses many more features. Per-game totals should be on the
same scale (both are fit to goals), but the per-shot spread differs, so
high_danger_xg_share in particular will not match MoneyPuck's exactly.

Per-game results are cached forever under cache/nhl_pbp_xg/: a completed
game's play-by-play doesn't change, and the cache is tiny (aggregates only).
"""

import json
import math
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

from .moneypuck_data import HIGH_DANGER_XG_THRESHOLD, _new_team_totals
from .nhl_data import BASE_URL, CACHE_DIR

XG_MODEL_PATH = (Path(__file__).resolve().parents[3]
                 / "xgcalc" / "web" / "xg_model.json")
PBP_CACHE_DIR = CACHE_DIR / "nhl_pbp_xg"

GOAL_LINE_X = 89.0
REBOUND_SECONDS = 3
PULL_TIME_SECONDS = 3000  # same rule as xgcalc/src/data/clean.py

SHOT_EVENTS = {"shot-on-goal", "missed-shot", "goal"}
# Events that can set up a rebound. MoneyPuck counts a shot as a rebound
# when the previous event was a shot attempt within 3 seconds.
REBOUND_SOURCES = {"shot-on-goal", "missed-shot", "blocked-shot"}

SHOT_TYPES = {
    "wrist": "WRIST", "snap": "SNAP", "slap": "SLAP", "backhand": "BACK",
    "tip-in": "TIP", "deflected": "DEFL", "wrap-around": "WRAP",
}

_MODEL = None


def _load_model() -> dict:
    global _MODEL
    if _MODEL is None:
        _MODEL = json.loads(XG_MODEL_PATH.read_text())
    return _MODEL


def score_shot(distance: float, angle: float, shot_type: str,
               is_rebound: int, situation: str) -> float:
    """P(goal) from the exported xgcalc logistic model, computed exactly as
    the sklearn pipeline does (scaler, one-hot with unknowns as all-zero)."""
    m = _load_model()
    coef = dict(zip(m["columns"], m["coef"]))
    logit = m["intercept"]
    num = m["numeric"]
    for name, value in zip(num["names"], (distance, angle, is_rebound)):
        i = num["names"].index(name)
        logit += coef[f"num__{name}"] * (value - num["mean"][i]) / num["scale"][i]
    cats = m["categorical"]["columns"]
    for feature, value in (("shot_type", shot_type), ("situation", situation)):
        col = cats[feature].get(value)
        if col is not None:
            logit += coef[col]
    return 1.0 / (1.0 + math.exp(-logit))


def _mmss(s: str) -> int:
    m, sec = s.split(":")
    return int(m) * 60 + int(sec)


def _situation(shoot_sk: int, def_sk: int, shooter_net_empty: bool,
               net_empty: bool, pulled: bool) -> str:
    """Port of the situation block in xgcalc/src/data/clean.py."""
    if net_empty:
        return "EN_AGAINST"
    state = f"{shoot_sk}v{def_sk}"
    if shooter_net_empty:
        if state == "6v5":
            return "EN_6v5_PULLED" if pulled else "EN_6v5_DELAYED_PEN"
        return "EN_OTHER_PULLED" if pulled else "EN_OTHER_DELAYED_PEN"
    named = {"5v5": "EV_5v5", "5v4": "PP_5v4", "4v5": "SH_4v5",
             "4v4": "EV_4v4", "3v3": "EV_3v3", "5v3": "PP_5v3",
             "4v3": "PP_4v3"}
    if state in named:
        return named[state]
    if shoot_sk > def_sk:
        return "PP_OTHER"
    if shoot_sk < def_sk:
        return "SH_OTHER"
    return "OTHER"


def game_team_xg(pbp: dict) -> dict:
    """Aggregate one game's play-by-play JSON (api-web.nhle.com
    /gamecenter/{id}/play-by-play) to {team_abbrev: totals}."""
    home_id, away_id = pbp["homeTeam"]["id"], pbp["awayTeam"]["id"]
    abbrev = {home_id: pbp["homeTeam"]["abbrev"],
              away_id: pbp["awayTeam"]["abbrev"]}
    teams = {abbrev[home_id]: _new_team_totals(True),
             abbrev[away_id]: _new_team_totals(False)}

    home_goals = away_goals = 0
    prev = None  # (type, team_id, period, elapsed)
    plays = sorted(pbp.get("plays", []), key=lambda p: p.get("sortOrder", 0))
    for p in plays:
        kind = p.get("typeDescKey")
        period_desc = p.get("periodDescriptor", {})
        period = period_desc.get("number", 0)
        if period_desc.get("periodType") == "SO":
            break  # shootout attempts are not shots
        d = p.get("details", {}) or {}
        team_id = d.get("eventOwnerTeamId")
        elapsed = (period - 1) * 1200 + _mmss(p.get("timeInPeriod", "00:00"))

        if kind in SHOT_EVENTS and team_id in abbrev:
            x, y = d.get("xCoord"), d.get("yCoord")
            code = p.get("situationCode") or ""
            if x is not None and y is not None and len(code) == 4:
                is_home = team_id == home_id
                away_g, away_sk, home_sk, home_g = (int(c) for c in code)

                # Which net the shooter attacks. homeTeamDefendingSide is
                # per-play; zoneCode (O/D/N from the shooter's view) is the
                # fallback when it's missing.
                side = p.get("homeTeamDefendingSide")
                if side in ("left", "right"):
                    attack_right = (side == "left") == is_home
                elif d.get("zoneCode") == "D":
                    attack_right = x < 0
                else:
                    attack_right = x >= 0
                x_adj = x if attack_right else -x
                y_abs = abs(y)

                distance = math.hypot(GOAL_LINE_X - x_adj, y_abs)
                angle = math.degrees(math.atan2(y_abs, GOAL_LINE_X - x_adj))
                shot_type = SHOT_TYPES.get(d.get("shotType"), "UNKNOWN")
                is_rebound = int(
                    prev is not None and prev[0] in REBOUND_SOURCES
                    and prev[1] == team_id and prev[2] == period
                    and 0 <= elapsed - prev[3] <= REBOUND_SECONDS)

                shoot_sk, def_sk = (home_sk, away_sk) if is_home else (away_sk, home_sk)
                shooter_net_empty = (home_g if is_home else away_g) == 0
                net_empty = (away_g if is_home else home_g) == 0
                diff = (home_goals - away_goals) * (1 if is_home else -1)
                pulled = (shooter_net_empty
                          and not (prev and prev[0] == "delayed-penalty")
                          and diff < 0 and elapsed >= PULL_TIME_SECONDS)
                situation = _situation(shoot_sk, def_sk, shooter_net_empty,
                                       net_empty, pulled)

                xg = score_shot(distance, angle, shot_type, is_rebound, situation)
                shooter = teams[abbrev[team_id]]
                defender = teams[abbrev[away_id if is_home else home_id]]
                shooter["xgf"] += xg
                defender["xga"] += xg
                # Same "5v5 close" filter as moneypuck_data, which checks
                # raw skater counts and the score before the shot.
                if home_sk == 5 and away_sk == 5 and abs(home_goals - away_goals) <= 1:
                    shooter["xgf_adj"] += xg
                    defender["xga_adj"] += xg
                if xg >= HIGH_DANGER_XG_THRESHOLD:
                    shooter["hd_xgf"] += xg
                    defender["hd_xga"] += xg

        if kind == "goal":
            if team_id == home_id:
                home_goals += 1
            elif team_id == away_id:
                away_goals += 1
        prev = (kind, team_id, period, elapsed)

    return teams


def _fetch_one(game_id: int):
    path = PBP_CACHE_DIR / f"{game_id}.json"
    if path.exists():
        return game_id, json.loads(path.read_text())
    url = f"{BASE_URL}/gamecenter/{game_id}/play-by-play"
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            break
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    teams = game_team_xg(resp.json())
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(teams))
    tmp.replace(path)
    return game_id, teams


def load_pbp_xg(game_ids: list, workers: int = 8) -> dict:
    """xG for each completed game in `game_ids`, from cache or the NHL API.
    A game that can't be fetched is skipped with a count, not raised: this
    is the serving fallback, and a missing game just contributes no xG
    update (see build_live_state)."""
    PBP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if not XG_MODEL_PATH.exists():
        print(f"  Warning: {XG_MODEL_PATH} missing, no play-by-play xG fallback")
        return {}
    out, failed = {}, 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(_fetch_one, gid) for gid in game_ids]
        for f in futures:
            try:
                gid, teams = f.result()
                out[gid] = teams
            except (requests.RequestException, ValueError, KeyError) as e:
                failed += 1
                last_err = e
    if failed:
        print(f"  Warning: play-by-play xG failed for {failed}/{len(game_ids)} "
              f"games (last error: {last_err})")
    return out
