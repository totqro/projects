"""
Projected Stanley Cup bracket — what the model said in April, scored in June.
============================================================================
Takes the actual first-round matchups, projects the whole bracket forward
with the shipped win model, and scores each slot against what actually
happened. Writes data/playoff_bracket.json for the web bracket view.

The projection is point-in-time, and that is the entire discipline here:

  * The model is the shipped xG drop-goalie logistic + Platt calibrator
    (ml_models/), whose training set is REGULAR SEASON ONLY — it has never
    seen a playoff game.
  * Team features come from replaying regular-season games only
    (fetch_season_games_full filters to gameType 2), so every team's state is
    frozen as of the end of the regular season — the day before the playoffs
    began. No playoff result feeds back into a projection of itself.
  * Probabilities come from xg_production.compute_serving_features() +
    predict_calibrated(), the same code path main.py serves daily, rather
    than a bracket-specific reimplementation.

Rounds are projected forward, not re-seeded from reality: our projected
first-round winners meet each other in round 2, and so on. A slot is correct
only if our projected winner is the team that actually won that slot — so
being "right" in round 3 requires having been right about who got there.

Series probabilities are exact, not simulated: all 2^7 game sequences are
enumerated with the 2-2-1-1-1 home-ice pattern, which also yields the exact
series-length distribution used for the Final's projected goal total.

Usage:
    python playoff_bracket.py                    # most recent completed playoffs
    python playoff_bracket.py --season 20252026
    python playoff_bracket.py --json data/playoff_bracket.json
"""

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

from src.data.historical_dataset import (
    MONEYPUCK_SEASONS,
    build_live_state,
    fetch_season_games_full,
    seasons_through_current,
)
from src.data.moneypuck_data import load_moneypuck_xg
from src.models import xg_production

BASE = Path(__file__).resolve().parent
DEFAULT_OUT = BASE / "data" / "playoff_bracket.json"
TRAINING_SET = BASE / "data" / "training_set.csv"

API = "https://api-web.nhle.com/v1"

# Home-ice pattern for a best-of-7: games 1, 2, 5, 7 at the higher seed.
HOME_ICE_PATTERN = [True, True, False, False, True, False, True]

# Playoff series play every other day. Both teams get the same value, so this
# cancels in rest_diff; it exists because the feature vector requires it.
PLAYOFF_REST_DAYS = 2

ROUND_LABELS = {1: "First Round", 2: "Second Round", 3: "Conference Final",
                4: "Stanley Cup Final"}


# --------------------------------------------------------------------------- #
# Actual bracket (NHL API)                                                     #
# --------------------------------------------------------------------------- #
def fetch_actual_bracket(season: str) -> list:
    """Every actual series, as [{round, letter, top, bottom, top_wins,
    bottom_wins, winner, loser}]. `top` is the higher seed (home ice)."""
    data = requests.get(f"{API}/playoff-series/carousel/{season}/", timeout=20).json()

    series = []
    for rnd in data.get("rounds", []):
        for s in rnd.get("series", []):
            top, bottom = s.get("topSeed", {}), s.get("bottomSeed", {})
            if not top.get("abbrev") or not bottom.get("abbrev"):
                continue  # a round that hasn't been drawn yet
            winner_id = s.get("winningTeamId")
            winner = None
            if winner_id == top.get("id"):
                winner = top["abbrev"]
            elif winner_id == bottom.get("id"):
                winner = bottom["abbrev"]
            series.append({
                "round": s.get("roundNumber", rnd.get("roundNumber")),
                "letter": s.get("seriesLetter"),
                "top": top["abbrev"],
                "bottom": bottom["abbrev"],
                "top_wins": top.get("wins", 0),
                "bottom_wins": bottom.get("wins", 0),
                "winner": winner,
            })
    return series


def fetch_series_games(season: str, letter: str) -> list:
    """Completed games in one series, as [{home, away, home_score, away_score}]."""
    r = requests.get(f"{API}/schedule/playoff-series/{season}/{letter.lower()}/", timeout=20)
    r.raise_for_status()
    games = []
    for g in r.json().get("games", []):
        if g.get("gameState") not in ("OFF", "FINAL"):
            continue
        home, away = g.get("homeTeam", {}), g.get("awayTeam", {})
        if home.get("score") is None or away.get("score") is None:
            continue
        games.append({
            "home": home.get("abbrev"), "away": away.get("abbrev"),
            "home_score": home.get("score"), "away_score": away.get("score"),
        })
    return games


def fetch_conferences(season: str) -> dict:
    """{team_abbrev: 'Eastern'|'Western'} from the end-of-regular-season
    standings — the bracket's left/right split."""
    end_year = int(season[4:])
    data = requests.get(f"{API}/standings/{end_year}-04-15", timeout=20).json()
    out = {}
    for row in data.get("standings", []):
        abbrev = (row.get("teamAbbrev") or {}).get("default")
        if abbrev:
            out[abbrev] = row.get("conferenceName")
    return out


# --------------------------------------------------------------------------- #
# Point-in-time model state                                                    #
# --------------------------------------------------------------------------- #
def build_pre_playoff_state(season: str, verbose: bool = True) -> dict:
    """Replay every completed REGULAR-SEASON game through `season` and return
    the state dict xg_production.compute_serving_features() expects.

    Deliberately not xg_production.get_live_feature_state(): that keys state
    to the *current* season, which after July 1 is the next one — every team
    would snapshot to a neutral prior and every series would come out 50/50."""
    seasons = [s for s in seasons_through_current("20222023") if s <= season]

    all_games = []
    for s in seasons:
        all_games.extend(fetch_season_games_full(s, verbose=verbose))

    xg_seasons = sorted(set(seasons) & MONEYPUCK_SEASONS)
    xg_data = load_moneypuck_xg(xg_seasons) if xg_seasons else {}
    team_states, h2h_results = build_live_state(all_games, xg_data=xg_data)

    return {
        "team_states": team_states,
        "h2h_results": h2h_results,
        "current_season": season,
        "as_of_date": max((g["date"] for g in all_games), default=""),
    }


def league_average_total(season: str, csv_path: Path = TRAINING_SET) -> float:
    """Mean regular-season total goals through `season` — the league-average
    Poisson baseline. This is the *only* totals model that has ever passed the
    totals gate (model_gate.py --totals beats every candidate with it), so it
    is what the bracket claims about goals, rather than an ungated guess."""
    totals = []
    with open(csv_path) as f:
        for row in csv.DictReader(f):
            if row["season"] <= season:
                totals.append(float(row["total_goals"]))
    if not totals:
        raise ValueError(f"No training rows at or before season {season}")
    return sum(totals) / len(totals)


# --------------------------------------------------------------------------- #
# Series math                                                                  #
# --------------------------------------------------------------------------- #
def game_probability(state, coefs, calibrator, home: str, away: str) -> float:
    """Calibrated P(home wins) for one playoff game, via production's own
    feature builder and calibrated predictor."""
    features = xg_production.compute_serving_features(
        state, home, away,
        PLAYOFF_REST_DAYS, PLAYOFF_REST_DAYS, False, False)
    p_cal, _ = xg_production.predict_calibrated(coefs, calibrator, features)
    return p_cal


def series_outcome(p_top_at_home: float, p_top_on_road: float) -> dict:
    """Exact best-of-7 result by enumerating every game sequence.

    Returns P(top seed wins the series) and the expected number of games —
    both exact, since a best-of-7 has at most 2^7 paths."""
    p_series = 0.0
    expected_games = 0.0
    length_probs = {4: 0.0, 5: 0.0, 6: 0.0, 7: 0.0}

    def walk(game_idx: int, top_wins: int, bottom_wins: int, prob: float):
        nonlocal p_series, expected_games
        if top_wins == 4 or bottom_wins == 4:
            games = top_wins + bottom_wins
            expected_games += prob * games
            length_probs[games] += prob
            if top_wins == 4:
                p_series += prob
            return
        p_top = p_top_at_home if HOME_ICE_PATTERN[game_idx] else p_top_on_road
        walk(game_idx + 1, top_wins + 1, bottom_wins, prob * p_top)
        walk(game_idx + 1, top_wins, bottom_wins + 1, prob * (1.0 - p_top))

    walk(0, 0, 0, 1.0)
    return {
        "p_top_wins": p_series,
        "expected_games": expected_games,
        "length_probs": length_probs,
    }


def project_series(state, coefs, calibrator, top: str, bottom: str) -> dict:
    """Project one matchup. `top` holds home ice (games 1/2/5/7)."""
    p_top_at_home = game_probability(state, coefs, calibrator, top, bottom)
    # On the road the top seed is the away team, so its win probability is
    # 1 - P(the other team wins at home).
    p_top_on_road = 1.0 - game_probability(state, coefs, calibrator, bottom, top)
    outcome = series_outcome(p_top_at_home, p_top_on_road)

    top_wins = outcome["p_top_wins"] >= 0.5
    return {
        "top": top,
        "bottom": bottom,
        "p_top_wins_series": outcome["p_top_wins"],
        "p_top_game_home": p_top_at_home,
        "p_top_game_road": p_top_on_road,
        "projected_winner": top if top_wins else bottom,
        "projected_winner_prob": outcome["p_top_wins"] if top_wins else 1 - outcome["p_top_wins"],
        "expected_games": outcome["expected_games"],
    }


# --------------------------------------------------------------------------- #
# Bracket projection                                                           #
# --------------------------------------------------------------------------- #
def _points_pct(state, team: str) -> float:
    from src.data.historical_dataset import snapshot_team_state
    snap = snapshot_team_state(state["team_states"], state["current_season"],
                               team, state["as_of_date"])
    return snap["points_pct"]


def home_ice(state, actual_by_round: dict, rnd: int, a: str, b: str) -> tuple:
    """(top, bottom) for a projected matchup. If this matchup actually
    happened, reality already settled who had home ice; otherwise the NHL's
    own rule applies — the better regular-season record hosts."""
    for s in actual_by_round.get(rnd, []):
        if {s["top"], s["bottom"]} == {a, b}:
            return s["top"], s["bottom"]
    return (a, b) if _points_pct(state, a) >= _points_pct(state, b) else (b, a)


def project_bracket(season: str, state, coefs, calibrator, actual: list,
                    conferences: dict) -> dict:
    """Walk the bracket forward from the actual first-round matchups, carrying
    OUR projected winners into later rounds, and score each slot."""
    actual_by_round = {}
    for s in actual:
        actual_by_round.setdefault(s["round"], []).append(s)

    max_round = max(actual_by_round)
    slots = []

    # Round 1: the real matchups.
    current = []
    for s in sorted(actual_by_round[1], key=lambda x: x["letter"]):
        proj = project_series(state, coefs, calibrator, s["top"], s["bottom"])
        current.append({"series": s, "projection": proj})
        slots.append(_slot(1, s, proj, conferences))

    # Rounds 2+: our projected winners advance and meet each other. Which two
    # slots feed a later slot is taken from reality's tree — the two previous
    # series whose actual participants make up this series' actual pairing.
    for rnd in range(2, max_round + 1):
        nxt = []
        for s in sorted(actual_by_round[rnd], key=lambda x: x["letter"]):
            parents = [c for c in current
                       if {c["series"]["top"], c["series"]["bottom"]} & {s["top"], s["bottom"]}]
            if len(parents) != 2:
                # Reality's tree can't be reconstructed for this slot (a
                # cancelled or re-seeded round); fall back to the actual
                # matchup so the bracket still renders, and say so.
                proj = project_series(state, coefs, calibrator, s["top"], s["bottom"])
                nxt.append({"series": s, "projection": proj})
                slots.append(_slot(rnd, s, proj, conferences, tree_broken=True))
                continue

            a = parents[0]["projection"]["projected_winner"]
            b = parents[1]["projection"]["projected_winner"]
            top, bottom = home_ice(state, actual_by_round, rnd, a, b)
            proj = project_series(state, coefs, calibrator, top, bottom)
            nxt.append({"series": s, "projection": proj})
            slots.append(_slot(rnd, s, proj, conferences))
        current = nxt

    return {"slots": slots, "max_round": max_round}


def _slot(rnd: int, actual_series: dict, proj: dict, conferences: dict,
          tree_broken: bool = False) -> dict:
    """One bracket position: what we projected, what happened, and whether the
    projection was right. Wrong-team-entirely and wrong-winner both score as a
    miss — there is no partial credit for picking a team that never got here."""
    actual_winner = actual_series["winner"]
    projected_winner = proj["projected_winner"]
    correct = actual_winner is not None and projected_winner == actual_winner

    # Conference for layout: rounds 1-3 sit inside one conference; the Final
    # is cross-conference and rendered in the middle.
    conf = conferences.get(actual_series["top"]) if rnd < 4 else None

    return {
        "round": rnd,
        "round_label": ROUND_LABELS.get(rnd, f"Round {rnd}"),
        "letter": actual_series["letter"],
        "conference": conf,
        "projected_matchup": [proj["top"], proj["bottom"]],
        "projected_winner": projected_winner,
        "projected_winner_prob": proj["projected_winner_prob"],
        "projected_games": proj["expected_games"],
        "actual_matchup": [actual_series["top"], actual_series["bottom"]],
        "actual_winner": actual_winner,
        "actual_result": f"{actual_series['top_wins']}-{actual_series['bottom_wins']}",
        "correct": correct,
        "tree_reconstructed_from_actual": tree_broken,
    }


def final_totals(season: str, slots: list, avg_total: float) -> dict:
    """Projected vs actual goals for the Stanley Cup Final.

    Projected per-game goals is the league-average Poisson baseline (the only
    totals model that has passed the totals gate); the series total is that
    figure times the model's own projected series length, so nothing here
    borrows the actual number of games."""
    final_slot = next((s for s in slots if s["round"] == 4), None)
    if not final_slot:
        return {}

    games = fetch_series_games(season, final_slot["letter"])
    actual_total = sum(g["home_score"] + g["away_score"] for g in games)

    return {
        "projected_per_game": avg_total,
        "projected_games": final_slot["projected_games"],
        "projected_series_total": avg_total * final_slot["projected_games"],
        "actual_per_game": (actual_total / len(games)) if games else None,
        "actual_games": len(games),
        "actual_series_total": actual_total,
        "basis": "league-average Poisson baseline (the totals gate's winner) "
                 "x the model's projected series length",
    }


def build(season: str, verbose: bool = True) -> dict:
    if not xg_production.production_model_exists():
        raise SystemExit(
            "No persisted xG model in ml_models/ — run build_training_set.py first. "
            "Refusing to project a bracket with a model that isn't the shipped one.")

    coefs, calibrator = xg_production.load_production_model()
    actual = fetch_actual_bracket(season)
    if not actual:
        raise SystemExit(f"No playoff series found for season {season}.")

    conferences = fetch_conferences(season)
    if verbose:
        print(f"  Replaying regular-season games through {season}...")
    state = build_pre_playoff_state(season, verbose=verbose)
    avg_total = league_average_total(season)

    result = project_bracket(season, state, coefs, calibrator, actual, conferences)
    slots = result["slots"]
    scored = [s for s in slots if s["actual_winner"]]

    return {
        "season": season,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "model": "xg-dropgoalie-platt-v1",
        "state_as_of": state["as_of_date"],
        "methodology": (
            "Projected forward from the actual first-round matchups using the "
            "shipped xG model, with team state frozen at the end of the regular "
            "season. The model's training set is regular season only, so no "
            "playoff result informs any projection of it."),
        "summary": {
            "correct": sum(1 for s in scored if s["correct"]),
            "scored": len(scored),
        },
        "slots": slots,
        "final_totals": final_totals(season, slots, avg_total),
    }


def print_report(card: dict) -> None:
    print("=" * 78)
    print(f"  PROJECTED STANLEY CUP BRACKET — {card['season']}")
    print("=" * 78)
    print(f"  Model: {card['model']}   State frozen at: {card['state_as_of']}")
    summary = card["summary"]
    print(f"  Correct slots: {summary['correct']} / {summary['scored']}")
    print("-" * 78)
    for rnd in sorted({s["round"] for s in card["slots"]}):
        print(f"\n  {ROUND_LABELS.get(rnd, rnd)}")
        for s in [x for x in card["slots"] if x["round"] == rnd]:
            mark = "✅" if s["correct"] else "❌"
            matchup = " vs ".join(s["projected_matchup"])
            line = (f"    {mark} {s['projected_winner']:<4} "
                    f"({s['projected_winner_prob']:.0%})  projected {matchup}")
            if not s["correct"]:
                line += (f"   — actual: {s['actual_winner']} "
                         f"({' vs '.join(s['actual_matchup'])} {s['actual_result']})")
            print(line)

    t = card.get("final_totals") or {}
    if t:
        print("\n  Stanley Cup Final — total goals")
        print(f"    Projected: {t['projected_per_game']:.2f}/game x "
              f"{t['projected_games']:.1f} games = {t['projected_series_total']:.1f}")
        print(f"    Actual:    {t['actual_per_game']:.2f}/game x "
              f"{t['actual_games']} games = {t['actual_series_total']}")
    print("-" * 78)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--season", default=None,
                        help="Playoff season, e.g. 20252026 (default: most "
                             "recently completed)")
    parser.add_argument("--json", dest="json_path", default=str(DEFAULT_OUT),
                        help=f"Where to write the bracket JSON (default: {DEFAULT_OUT})")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    season = args.season
    if not season:
        # After July 1 the "current" season hasn't been played; the most
        # recently completed playoffs are the previous season's.
        current = seasons_through_current("20222023")[-1]
        season = f"{int(current[:4]) - 1}{int(current[4:]) - 1}"

    card = build(season, verbose=not args.quiet)
    print_report(card)

    out = Path(args.json_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(card, indent=2))
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
