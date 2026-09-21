"""
Performance history by season — what the site's Performance tab reads.
======================================================================
One entry ("period") per season and phase (regular season / preseason), newest
first, each with its own accuracy, log loss, Brier and per-game rows.

Two kinds of period, deliberately treated differently:

  backtest  A finished season scored by the SHIPPED model on data it did not
            train on (model_backtest.py). FROZEN: imported once from
            data/model_backtest_<season>.json and never recomputed. The
            weekly refit will eventually fold that season into training,
            after which re-running the backtest would report in-sample
            numbers as if they were a fair test; the frozen record can't
            drift that way.

  live      Predictions from data/predictions_log.jsonl scored against real
            results (and the market's closing line where one exists), rebuilt
            on every run. Only rows logged before the game date count — the
            scorecard's rule 1, reused via scorecard.load_predictions.

Preseason is its own period, never pooled with the regular season: preseason
lineups are prospect-heavy and say nothing about the model the scorecard
validates. It is shown, and scored, for interest only.

Replaces the old Performance tab source (backtest_results.json), which came
from backtest.py — a similarity model that no longer ships.

Usage:
    python performance_history.py            # rebuild data/performance_history.json
    python performance_history.py --print    # summary to stdout, write nothing
"""

import argparse
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scorecard import (
    MEANINGFUL_SAMPLE, PREDICTIONS_LOG, REGULAR_SEASON, build_rows, fetch_actuals,
    load_market, load_predictions, season_bounds, totals_metrics, win_metrics,
)

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
OUT_PATH = DATA / "performance_history.json"
PRESEASON = 1
EST = timezone(timedelta(hours=-4))

PHASES = {
    REGULAR_SEASON: ("regular", "Regular season"),
    PRESEASON: ("preseason", "Preseason"),
}


def season_of(date: str) -> str:
    """'2026-09-21' -> '20262027'. Same July 1 boundary as scorecard.season_bounds."""
    year, month = int(date[:4]), int(date[5:7])
    start = year if month >= 7 else year - 1
    return f"{start}{start + 1}"


def season_label(season: str) -> str:
    return f"{season[:4]}-{season[6:]}"


def _clean(obj):
    """NaN/inf -> None, recursively. json.dump would emit bare NaN, which is
    not JSON and makes the browser's response.json() throw."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return obj


def _game_row(date, home, away, p_home, home_win, pred_total, total_goals) -> dict:
    return {
        "date": date,
        "home": home,
        "away": away,
        "p_home": round(float(p_home), 4),
        "home_win": home_win,
        "pred_total": round(float(pred_total), 2) if pred_total is not None else None,
        "total_goals": total_goals,
    }


def _summarize(games: list) -> dict:
    """Win and totals metrics over the games that have a result."""
    done = [g for g in games if g["home_win"] is not None]
    win = win_metrics([g["p_home"] for g in done], [g["home_win"] for g in done])
    with_total = [g for g in done if g["pred_total"] is not None]
    totals = totals_metrics([g["pred_total"] for g in with_total],
                            [g["total_goals"] for g in with_total])
    if with_total:
        off = [abs(round(g["pred_total"]) - g["total_goals"]) for g in with_total]
        totals["within_1"] = sum(1 for d in off if d <= 1) / len(off)
        totals["exact"] = sum(1 for d in off if d == 0) / len(off)
    return {"win": win, "totals": totals}


# --------------------------------------------------------------------------- #
# Frozen backtest periods                                                      #
# --------------------------------------------------------------------------- #
def import_backtest(path: Path) -> dict:
    """One frozen 'regular season' period from a model_backtest.py JSON."""
    bt = json.loads(path.read_text())
    season = bt["season"]
    mu = (bt.get("totals") or {}).get("baseline_per_game")
    games = [
        _game_row(g["date"], g["home_team"], g["away_team"], g["xg_home_win_prob"],
                  int(g["home_win"]), mu, int(g["total_goals"]))
        for g in sorted(bt["games"], key=lambda g: g["date"], reverse=True)
    ]
    summary = _summarize(games)
    elo = ((bt.get("win") or {}).get("head_to_head") or {}).get("elo") or {}
    prov = bt.get("provenance") or {}
    note = (
        "Held-out backtest: the shipped xG model, trained on "
        f"{', '.join(season_label(s) for s in prov.get('trained_on_seasons', []))}, "
        "scored game by game on a season it never trained on. Total goals is the "
        "league-average baseline — the only totals forecast that passed the gate."
    )
    if bt.get("calibration_season_caveat"):
        note += (" Caveat: the probability calibrator was fit on this exact season, "
                 "so its calibration is not blind; the winner picks are.")
    return {
        "id": f"{season}-regular",
        "season": season,
        "label": season_label(season),
        "phase": "regular",
        "phase_label": "Regular season",
        "source": "backtest",
        "frozen": True,
        "status": "complete",
        "note": note,
        "model_versions": {"xg-dropgoalie-platt-v1": len(games)},
        "n_games": len(games),
        "n_pending": 0,
        "win": summary["win"],
        "totals": summary["totals"],
        "benchmarks": {"elo": elo, "market": None, "market_n": 0,
                       "market_meaningful": False},
        "games": games,
    }


# --------------------------------------------------------------------------- #
# Live periods                                                                 #
# --------------------------------------------------------------------------- #
def build_live_periods(today: str, predictions_log: Path = PREDICTIONS_LOG) -> list:
    """Live periods from the prediction log, one per (season, phase) present."""
    preds = load_predictions(path=predictions_log,
                             game_types=(REGULAR_SEASON, PRESEASON))
    if not preds:
        return []

    dates = {key[0] for key in preds if key[0] <= today}
    actuals, failed = fetch_actuals(dates, include_playoffs=True)
    if failed:
        print(f"  ⚠️  {len(failed)} date(s) had no results fetched: {failed}")
    market = load_market()

    by_period = {}
    for key, row in preds.items():
        game_type = row.get("game_type", REGULAR_SEASON)
        by_period.setdefault((season_of(key[0]), game_type), {})[key] = row

    periods = []
    for (season, game_type), rows in by_period.items():
        phase, phase_label = PHASES.get(game_type, (f"type{game_type}", f"Type {game_type}"))
        scored, _pending = build_rows(rows, actuals, market)
        scored_by_key = {(r["date"], r["home_team"], r["away_team"]): r for r in scored}

        games = []
        for key, row in rows.items():
            r = scored_by_key.get(key)
            games.append(_game_row(
                key[0], key[1], key[2], row["home_win_prob"],
                r["home_win"] if r else None,
                row.get("expected_total"),
                r["total_goals"] if r else None))
        games.sort(key=lambda g: (g["date"], g["home"]), reverse=True)

        summary = _summarize(games)
        h2h = [r for r in scored if r["market_home_win_prob"] is not None]
        market_block = None
        if h2h:
            ys = [r["home_win"] for r in h2h]
            market_block = {
                "model": win_metrics([r["model_home_win_prob"] for r in h2h], ys),
                "market": win_metrics([r["market_home_win_prob"] for r in h2h], ys),
            }

        lo, hi = season_bounds(season)
        n_done = sum(1 for g in games if g["home_win"] is not None)
        versions = {}
        for row in rows.values():
            v = row.get("model_version")
            versions[v] = versions.get(v, 0) + 1

        if game_type == PRESEASON:
            note = ("Preseason predictions, logged before puck drop and scored for "
                    "interest only. Lineups are prospect-heavy and every team starts "
                    "from last season's rating, so treat these as low-information. "
                    "They are not part of the season scorecard.")
        else:
            note = ("Live predictions, each logged before puck drop and scored "
                    "against the final result.")
        periods.append({
            "id": f"{season}-{phase}",
            "season": season,
            "label": season_label(season),
            "phase": phase,
            "phase_label": phase_label,
            "source": "live",
            "frozen": False,
            "status": "in_progress" if today <= hi else "complete",
            "note": note,
            "model_versions": versions,
            "n_games": n_done,
            "n_pending": len(games) - n_done,
            "win": summary["win"],
            "totals": summary["totals"],
            "benchmarks": {
                "elo": None,
                "market": market_block,
                "market_n": len(h2h),
                "market_meaningful": len(h2h) >= MEANINGFUL_SAMPLE,
            },
            "games": games,
        })
    return periods


# --------------------------------------------------------------------------- #
# Assembly                                                                     #
# --------------------------------------------------------------------------- #
def _period_sort_key(p: dict) -> tuple:
    # Newest season first; within a season the regular season leads the
    # preseason that precedes it, since that is the record that matters.
    return (p["season"], 1 if p["phase"] == "regular" else 0)


def build(today: str = None, out_path: Path = OUT_PATH,
          backtest_dir: Path = DATA, predictions_log: Path = PREDICTIONS_LOG) -> dict:
    today = today or datetime.now(EST).strftime("%Y-%m-%d")

    existing = {}
    if out_path.exists():
        try:
            existing = {p["id"]: p for p in json.loads(out_path.read_text()).get("periods", [])}
        except (json.JSONDecodeError, KeyError):
            existing = {}

    periods = {pid: p for pid, p in existing.items() if p.get("frozen")}
    for path in sorted(backtest_dir.glob("model_backtest_*.json")):
        pid = f"{json.loads(path.read_text())['season']}-regular"
        if pid not in periods:
            print(f"  Freezing backtest period {pid} from {path.name}")
            periods[pid] = import_backtest(path)

    for p in build_live_periods(today, predictions_log):
        # A frozen backtest owns its (season, phase); a live row for the same
        # slot would mean the log overlaps a season we already scored offline.
        periods.setdefault(p["id"], p)

    ordered = sorted(periods.values(), key=_period_sort_key, reverse=True)
    return _clean({
        "generated_at": datetime.now(EST).isoformat(),
        "periods": ordered,
    })


def main():
    parser = argparse.ArgumentParser(description="Build the by-season performance history")
    parser.add_argument("--print", action="store_true",
                        help="Print a summary instead of writing the JSON")
    args = parser.parse_args()

    result = build()
    for p in result["periods"]:
        acc = p["win"].get("accuracy")
        print(f"  {p['label']} {p['phase_label']:<15} {p['source']:<8} "
              f"{p['n_games']:>5} scored, {p['n_pending']:>3} pending"
              + (f"  accuracy {acc:.1%}" if acc is not None else ""))
    if args.print:
        return
    OUT_PATH.write_text(json.dumps(result, separators=(",", ":")))
    print(f"Wrote {OUT_PATH} ({OUT_PATH.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
