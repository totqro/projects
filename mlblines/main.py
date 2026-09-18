#!/usr/bin/env python3
"""
MLB game predictions
====================
Scores today's games with the gated models from build_training_set.py:

  * win probability — the pitcher-aware logistic (probable starters, bullpens,
    Elo, shrunk run differential), shipped only because it beats Elo + home
    field on held-out log loss and Brier in every season tested
  * expected total runs — negative-binomial GLM, shipped only because it beats
    the league average on held-out RMSE and likelihood

Every input is pre-game. The market's devigged consensus is shown next to the
model as the benchmark, not blended into it.

Outputs:
  mlbdata/latest_analysis.json     what the site renders
  mlbdata/predictions_log.jsonl    append-only record, written before first pitch
  mlbdata/analysis_history.json    rolling 30 days of runs (used by bet_tracker)

Usage:
    python main.py                # with live odds
    python main.py --no-odds      # model only
    python main.py --date 2026-09-18
"""

import argparse
import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
warnings.filterwarnings("ignore", category=RuntimeWarning)

from src.analysis.analysis_history import save_analysis
from src.analysis.prediction_log import log_predictions
from src.data.mlb_data import get_pitcher_stats
from src.data.odds_fetcher import (
    fetch_mlb_odds, get_best_odds, get_consensus_no_vig_odds, parse_odds, team_name_to_abbrev,
)
from src.models.totals_model import over_probability
from src.serving import ET, score_slate

BASE = Path(__file__).resolve().parent
OUTPUT = BASE / "mlbdata" / "latest_analysis.json"
LEAGUE_FIP = 4.25


def _quality(fip: float) -> float:
    """0-100 display score from the model's shrunk starter FIP. 50 is league
    average; one standard deviation among starters is about 16 points."""
    return round(max(0.0, min(100.0, 50 + (LEAGUE_FIP - fip) * 40)), 1)


def _match_odds(games: list, odds_games: list) -> dict:
    """{game_id: odds game} matched on teams and closest commence time, so
    doubleheaders pair correctly."""
    out = {}
    for og in odds_games:
        home = team_name_to_abbrev(og["home_team"])
        away = team_name_to_abbrev(og["away_team"])
        commence = datetime.fromisoformat(og["commence_time"].replace("Z", "+00:00"))
        best, best_gap = None, None
        for g in games:
            if g["home_team"] != home or g["away_team"] != away or g["game_id"] in out:
                continue
            start = datetime.fromisoformat(g["game_datetime"].replace("Z", "+00:00"))
            gap = abs((start - commence).total_seconds())
            if gap < 6 * 3600 and (best_gap is None or gap < best_gap):
                best, best_gap = g, gap
        if best:
            out[best["game_id"]] = og
    return out


def _pitcher_card(pid, name: str, profile_fip: float, k_bb: float) -> dict:
    season = get_pitcher_stats(pid) if pid else {}
    return {
        "name": name or "TBD",
        "era": float(season.get("era", 4.50)),
        "whip": float(season.get("whip", 1.30)),
        "k_per_9": float(season.get("k_per_9", 8.0)),
        "fip": round(profile_fip, 2),
        "k_bb_pct": round(k_bb * 100, 1),
        "quality_score": _quality(profile_fip),
        "handedness": season.get("handedness", "R"),
        "announced": bool(pid),
    }


def run(use_odds: bool = True, date: str = None, stake: float = 0.50) -> dict:
    print("=" * 64)
    print("  MLB Game Predictions (gated, pre-game only)")
    print(f"  {datetime.now(ET).strftime('%A, %B %d %Y %H:%M ET')}")
    print("=" * 64)

    slate = score_slate(date=date)
    win_art, totals_art = slate["win_artifact"], slate["totals_artifact"]
    print(f"\nWin model: {win_art['model_version']} "
          f"(trained on {win_art['trained_on_seasons'][0]}-{win_art['trained_on_seasons'][-1]})")
    print(f"Totals model: {totals_art['model_version']}")

    now = datetime.now(timezone.utc)
    upcoming = [g for g in slate["games"]
                if datetime.fromisoformat(g["game_datetime"].replace("Z", "+00:00")) > now]
    started = len(slate["games"]) - len(upcoming)
    print(f"{slate['date']}: {len(slate['games'])} games, {len(upcoming)} not yet started"
          + (f" ({started} already underway, skipped)" if started else ""))

    odds_by_game, quota = {}, None
    if use_odds and upcoming:
        try:
            raw, quota = fetch_mlb_odds()
            odds_by_game = _match_odds(upcoming, parse_odds(raw))
            print(f"Market prices matched for {len(odds_by_game)} of {len(upcoming)} games")
        except Exception as e:
            print(f"Warning: could not fetch odds ({e}); publishing model only")

    analyses, picks, log_rows = [], [], []
    for g in upcoming:
        f = g["features"]
        home, away = g["home_team"], g["away_team"]
        p_home = g["home_win_prob"]
        mu = g["expected_total"]
        og = odds_by_game.get(g["game_id"])
        market = get_consensus_no_vig_odds(og) if og else None
        best = get_best_odds(og) if og else None
        total_line = market["total_line"] if market else None
        p_over = over_probability(mu, total_line, totals_art["dispersion"]) if total_line else None

        pick_home = p_home >= 0.5
        pick_team = home if pick_home else away
        pick_prob = p_home if pick_home else 1 - p_home

        model_probs = {
            "home_win_prob": p_home, "away_win_prob": 1 - p_home,
            "expected_total": mu, "total_line": total_line,
            "over_prob": p_over, "under_prob": (1 - p_over) if p_over is not None else None,
            "confidence": pick_prob,
        }
        market_probs = None
        if market:
            market_probs = {"home_win_prob": market["home_win_prob"],
                            "away_win_prob": market["away_win_prob"],
                            "over_prob": market["over_prob"], "total_line": total_line,
                            "n_books": market["n_books_ml"]}

        indicators = {"pitcher": [], "park": []}
        for team, side in ((home, "home"), (away, "away")):
            fip = f[f"{side}_sp_fip"]
            if not g[f"{side}_sp_id"]:
                indicators["pitcher"].append({"team": team, "type": "tbd", "severity": "medium"})
            elif _quality(fip) >= 70:
                indicators["pitcher"].append({"team": team, "type": "ace", "value": _quality(fip), "severity": "positive"})
            elif _quality(fip) <= 30:
                indicators["pitcher"].append({"team": team, "type": "weak", "value": _quality(fip), "severity": "negative"})
        park = round(f["park_factor"] * 100)
        if park >= 105:
            indicators["park"].append({"team": home, "type": "hitter-friendly", "value": park, "severity": "medium"})
        elif park <= 95:
            indicators["park"].append({"team": home, "type": "pitcher-friendly", "value": park, "severity": "medium"})

        label = f"{away} @ {home}"
        analysis = {
            "game": label, "home": home, "away": away, "game_id": g["game_id"],
            "game_time": g["game_datetime"],
            "model_probs": model_probs,
            "market_probs": market_probs,
            "pick": {"team": pick_team, "prob": pick_prob,
                     "agrees_with_market": (None if not market else
                                            (market["home_win_prob"] >= 0.5) == pick_home),
                     "edge_vs_market": (None if not market else
                                        pick_prob - (market["home_win_prob"] if pick_home else market["away_win_prob"]))},
            "context_indicators": indicators,
            "pitcher_matchup": {
                "home": _pitcher_card(g["home_sp_id"], g["home_sp_name"], f["home_sp_fip"], f["home_sp_k_bb"]),
                "away": _pitcher_card(g["away_sp_id"], g["away_sp_name"], f["away_sp_fip"], f["away_sp_k_bb"]),
            },
            "bullpen": {
                side: {"bullpen_ra9": round(rpo * 27, 2),
                       "bullpen_quality": round(max(0, min(100, 50 + (0.165 - rpo) * 1000)), 1)}
                for side, rpo in (("home", f["home_bullpen_rpo"]), ("away", f["away_bullpen_rpo"]))
            },
            "elo": {"home": round(f["home_elo"]), "away": round(f["away_elo"])},
            "park_factor": park,
        }
        analyses.append(analysis)

        if best and best["moneyline"]["home" if pick_home else "away"]:
            price = best["moneyline"]["home" if pick_home else "away"]
            fair = market["home_win_prob"] if pick_home else market["away_win_prob"]
            picks.append({
                "game": label, "bet_type": "Moneyline", "pick": f"{pick_team} ML",
                "book": price["book"], "odds": price["price"], "stake": stake,
                "true_prob": pick_prob, "implied_prob": fair, "edge": pick_prob - fair,
                "confidence": pick_prob, "model_version": win_art["model_version"],
            })

        log_rows.append({
            "game_id": g["game_id"], "date": g["date"], "game_datetime": g["game_datetime"],
            "home_team": home, "away_team": away,
            "home_sp_id": g["home_sp_id"], "away_sp_id": g["away_sp_id"],
            "home_win_prob": round(p_home, 5), "expected_total": round(mu, 3),
            "market_home_win_prob": market["home_win_prob"] if market else None,
            "market_total_line": total_line,
            "win_model_version": win_art["model_version"],
            "totals_model_version": totals_art["model_version"],
        })

        mk = f" | market {market['home_win_prob']:.1%}" if market else ""
        print(f"  {label:<11} {g['away_sp_name']:>20} vs {g['home_sp_name']:<20} "
              f"{home} {p_home:.1%}{mk} | total {mu:.1f}"
              + (f" (line {total_line}, over {p_over:.0%})" if total_line else ""))

    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "date": slate["date"],
        "model": {
            "win": win_art["model_version"], "totals": totals_art["model_version"],
            "win_gate": win_art.get("gate"), "totals_gate": totals_art.get("gate"),
            "trained_on_seasons": win_art["trained_on_seasons"],
            "fitted_at": win_art.get("fitted_at"),
        },
        "games_analyzed": analyses,
        "recommendations": picks,
        "quota_info": quota,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, indent=2, default=str))
    print(f"\nWrote {OUTPUT}")
    if log_rows:
        print(f"Logged {log_predictions(log_rows)} new prediction(s)")
    if analyses:
        save_analysis(output)
    return output


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-odds", action="store_true")
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default: today, US/Eastern)")
    ap.add_argument("--stake", type=float, default=0.50,
                    help="Nominal stake recorded on each pick for result tracking")
    args = ap.parse_args()
    run(use_odds=not args.no_odds, date=args.date, stake=args.stake)


if __name__ == "__main__":
    main()
