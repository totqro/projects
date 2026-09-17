#!/usr/bin/env python3
"""
Blind season backtest for the shipped MLB models.
=================================================
Scores one season game by game with models that never saw it:

  * the win model is the same model type and calibration choice as the
    shipped artifact (ml_models/win_model.json), refit on seasons BEFORE the
    backtest season only
  * the totals model likewise
  * every feature is the point-in-time row from mlbdata/training_set.csv

Benchmarks on the same games:
  * always pick the home team (constant = training seasons' home win rate)
  * Elo + home field, refit on the same prior seasons
  * the market: the devigged consensus from the latest archived snapshot taken
    strictly before first pitch (mlbdata/market_snapshots/). Only games with a
    pre-game snapshot are compared, and doubleheaders are skipped because a
    snapshot row can't be tied to one game of the pair.

Writes mlbdata/backtest_results.json, which the site's Performance tab renders.

Usage:
    python backtest.py                 # latest season in the training set
    python backtest.py --season 2025
"""

import argparse
import json
import sys
import warnings
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
warnings.filterwarnings("ignore", category=RuntimeWarning)

import numpy as np

from src.data.historical_dataset import fetch_pitcher_names, load_csv
from src.data.odds_fetcher import team_name_to_abbrev
from src.models import totals_model, win_model

BASE = Path(__file__).resolve().parent
TRAINING_SET = BASE / "mlbdata" / "training_set.csv"
SNAPSHOT_DIR = BASE / "mlbdata" / "market_snapshots"
OUT = BASE / "mlbdata" / "backtest_results.json"
ET = ZoneInfo("America/New_York")


def load_closing_market(snapshot_dir: Path = SNAPSHOT_DIR) -> dict:
    """{(ET date, home, away): home_win_prob} from the latest snapshot taken
    before commence. Keys seen for two different commence times (a
    doubleheader) are dropped."""
    closing, commences = {}, {}
    for path in sorted(snapshot_dir.glob("*.json")):
        try:
            snap = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        taken = datetime.fromisoformat(snap["timestamp_utc"])
        for g in snap.get("games", []):
            commence = datetime.fromisoformat(g["commence_time"].replace("Z", "+00:00"))
            if taken >= commence or g.get("home_win_prob") is None:
                continue
            key = (commence.astimezone(ET).strftime("%Y-%m-%d"),
                   team_name_to_abbrev(g["home_team"]), team_name_to_abbrev(g["away_team"]))
            commences.setdefault(key, set()).add(g["commence_time"][:13])
            prev = closing.get(key)
            if prev is None or taken > prev[0]:
                closing[key] = (taken, float(g["home_win_prob"]))
    return {k: v[1] for k, v in closing.items() if len(commences[k]) == 1}


def run(season: int = None) -> dict:
    rows = load_csv(TRAINING_SET)
    season = season or max(r["season"] for r in rows)
    shipped_win = win_model.load()
    shipped_totals = totals_model.load()

    win = win_model.fit_production(rows, shipped_win["model"],
                                   shipped_win["calibrator"]["method"] == "platt",
                                   holdout_season=season)
    elo = win_model.fit_production(rows, "elo", shipped_win["calibrator"]["method"] == "platt",
                                   holdout_season=season)
    totals = totals_model.fit_production(rows, shipped_totals["model"], holdout_season=season)
    prior = [r for r in rows if r["season"] < season]
    home_rate = float(np.mean([r["home_win"] for r in prior]))
    base_total = float(np.mean([r["total_runs"] for r in prior]))

    test = sorted((r for r in rows if r["season"] == season),
                  key=lambda r: (r["date"], r["game_id"]))
    market = load_closing_market()
    day_counts = Counter((r["date"], r["home_team"], r["away_team"]) for r in test)
    names = fetch_pitcher_names({r["home_sp_id"] for r in test} | {r["away_sp_id"] for r in test})

    results = []
    for r in test:
        p = win_model.predict(win, r)
        p_elo = win_model.predict(elo, r)
        mu = totals_model.predict(totals, r)
        key = (r["date"], r["home_team"], r["away_team"])
        mkt = market.get(key) if day_counts[key] == 1 else None
        home_won = bool(r["home_win"])
        pred_home = p >= 0.5

        def sp(side):
            pid = r[f"{side}_sp_id"]
            return names.get(int(pid), {}).get("name", "TBD") if pid else "TBD"

        results.append({
            "date": r["date"],
            "game": f"{r['away_team']} @ {r['home_team']}",
            "home": r["home_team"], "away": r["away_team"],
            "pitchers": f"{sp('away')} vs {sp('home')}",
            "predicted_home_win_prob": round(p, 4),
            "predicted_away_win_prob": round(1 - p, 4),
            "elo_home_win_prob": round(p_elo, 4),
            "market_home_win_prob": round(mkt, 4) if mkt is not None else None,
            "predicted_winner": r["home_team"] if pred_home else r["away_team"],
            "actual_winner": r["home_team"] if home_won else r["away_team"],
            "winner_correct": pred_home == home_won,
            "confidence": round(max(p, 1 - p), 4),
            "predicted_total": round(mu, 2),
            "actual_total": r["total_runs"],
            "total_error": round(abs(mu - r["total_runs"]), 2),
            "actual_score": f"{r['away_score']}-{r['home_score']}",
        })

    y = [int(x["actual_winner"] == x["home"]) for x in results]
    p_model = [x["predicted_home_win_prob"] for x in results]
    with_mkt = [(x, yy) for x, yy in zip(results, y) if x["market_home_win_prob"] is not None]
    actual_totals = [x["actual_total"] for x in results]
    pred_totals = [x["predicted_total"] for x in results]
    n = len(results)

    out = {
        "generated_at": datetime.now(ET).isoformat(),
        "season": season,
        "blind": True,
        "model_version": shipped_win["model_version"],
        "totals_model_version": shipped_totals["model_version"],
        "trained_on_seasons": win["trained_on_seasons"],
        "start_date": results[0]["date"] if results else None,
        "total_games": n,
        "skipped": 0,
        "winner_correct": sum(x["winner_correct"] for x in results),
        "winner_accuracy": round(sum(x["winner_correct"] for x in results) / n, 4),
        "avg_total_error": round(float(np.mean([x["total_error"] for x in results])), 3),
        "within_1_run": round(sum(x["total_error"] <= 1 for x in results) / n, 4),
        "within_2_runs": round(sum(x["total_error"] <= 2 for x in results) / n, 4),
        "benchmarks": {
            "model": win_model.win_metrics(p_model, y),
            "elo": win_model.win_metrics([x["elo_home_win_prob"] for x in results], y),
            "always_home": win_model.win_metrics([home_rate] * n, y),
        },
        "market_comparison": {
            "n": len(with_mkt),
            "model": win_model.win_metrics([x["predicted_home_win_prob"] for x, _ in with_mkt],
                                           [yy for _, yy in with_mkt]),
            "market": win_model.win_metrics([x["market_home_win_prob"] for x, _ in with_mkt],
                                            [yy for _, yy in with_mkt]),
        },
        "totals": {
            "model": totals_model.totals_metrics(pred_totals, actual_totals, totals["dispersion"]),
            "league_average": totals_model.totals_metrics([base_total] * n, actual_totals, totals["dispersion"]),
        },
        "reliability": win_model.reliability_table(p_model, y),
        "results": sorted(results, key=lambda x: x["date"], reverse=True),
    }
    OUT.write_text(json.dumps(out, indent=2))
    return out


def print_report(out: dict) -> None:
    print("=" * 72)
    print(f"  BLIND BACKTEST — {out['season']} ({out['total_games']} games), "
          f"models trained on {out['trained_on_seasons']}")
    print("=" * 72)
    print(f"{'Predictor':<28}{'n':>6}{'Acc':>8}{'Log loss':>11}{'Brier':>9}{'ECE':>8}")
    print("-" * 72)
    rows = [("Shipped model", out["benchmarks"]["model"]),
            ("Elo + home field", out["benchmarks"]["elo"]),
            ("Always home", out["benchmarks"]["always_home"])]
    mc = out["market_comparison"]
    if mc["n"]:
        rows += [("Model (market games)", mc["model"]), ("Market close", mc["market"])]
    for label, m in rows:
        print(f"{label:<28}{m['n']:>6}{m['accuracy']:>8.3f}{m['log_loss']:>11.4f}"
              f"{m['brier']:>9.4f}{m['ece']:>8.4f}")
    t = out["totals"]
    print("-" * 72)
    print(f"Totals RMSE: model {t['model']['rmse']:.3f} vs league average "
          f"{t['league_average']['rmse']:.3f}; NLL {t['model']['nb_nll']:.4f} vs "
          f"{t['league_average']['nb_nll']:.4f}")
    if mc["n"] and mc["n"] < 200:
        print(f"Market comparison covers only {mc['n']} games: treat the gap as noise.")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", type=int, default=None)
    args = ap.parse_args()
    print_report(run(args.season))
