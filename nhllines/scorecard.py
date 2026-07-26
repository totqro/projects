"""
Season scorecard — logged predictions vs actual results vs the market.
======================================================================
Everything before this point was scored on held-out *historical* seasons
(`model_gate.py`, `calibrate.py`). This scores the only evidence that
actually counts: probabilities that were written down before puck drop
(`data/predictions_log.jsonl`) against what happened, next to the market's
devigged consensus for the same games (`data/market_snapshots/`).

Three rules make the comparison honest:

1. **Only pre-game rows count.** A row whose run_date is after the game date
   is not a prediction and is dropped. Where several runs logged the same
   game, the last pre-game row wins — that's the prediction that stood when
   the puck dropped.
2. **The market gets the closing price.** For each game, the market column
   uses the latest snapshot taken strictly *before* commence time. A snapshot
   taken after the game started would let the benchmark peek.
3. **Head-to-head is scored on the intersection.** The model is scored on
   every game it predicted, but the model-vs-market table only uses games
   where both have a pre-game number. Comparing a model's 800 games against
   a market's 600 is not a comparison.

Mixed model versions are reported, never silently pooled: rows carry the win
model that served them, and a scorecard spanning a fallback period says so.

Usage:
    python scorecard.py                          # current season to date
    python scorecard.py --season 20262027
    python scorecard.py --model-version xg-dropgoalie-platt-v1
    python scorecard.py --json data/scorecard.json
"""

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss

from src.data.historical_dataset import current_season
from src.data.nhl_data import fetch_scores
from src.data.odds_fetcher import team_name_to_abbrev
from src.models.calibration import expected_calibration_error, reliability_table

# Same Poisson NLL the totals gate scores against the league-average baseline,
# imported rather than reimplemented so "the model beat the baseline" and "the
# model scored X this season" mean the same thing.
from model_gate import _poisson_nll as poisson_nll

BASE = Path(__file__).resolve().parent
PREDICTIONS_LOG = BASE / "data" / "predictions_log.jsonl"
SNAPSHOT_DIR = BASE / "data" / "market_snapshots"

# main.py stamps a game's date by converting the UTC commence time at this
# fixed offset (see main.py's EST constant). The market snapshots store raw
# UTC commence times, so they must be converted the same way or the join
# silently misses every late-evening game.
EST = timezone(timedelta(hours=-4))

# NHL gameType 2 = regular season. The shipped models are fit on regular
# season games only, so playoffs are excluded unless asked for.
REGULAR_SEASON = 2

# Below this many head-to-head games, a log-loss gap between the model and the
# market is not evidence of anything. The interim scorecard milestone is ~600
# games for that reason; this is the floor at which the comparison stops being
# pure noise, not a threshold at which it becomes conclusive.
MEANINGFUL_SAMPLE = 200


def _game_key(date: str, home: str, away: str) -> tuple:
    return (date, home, away)


def season_bounds(season: str) -> tuple:
    """('20262027') -> ('2026-07-01', '2027-06-30'), matching the July 1 season
    boundary used by historical_dataset.current_season()."""
    start = int(season[:4])
    return f"{start}-07-01", f"{start + 1}-06-30"


# --------------------------------------------------------------------------- #
# Inputs                                                                       #
# --------------------------------------------------------------------------- #
def load_predictions(path: Path = PREDICTIONS_LOG, season: str = None,
                     model_version: str = None) -> dict:
    """Read the prediction log and return {game_key: row}, keeping only the
    last pre-game row per game (rule 1). Rows are returned exactly as logged."""
    if not path.exists():
        return {}

    lo, hi = season_bounds(season) if season else (None, None)

    best = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue

        date = row.get("date")
        if not date or not row.get("home_team") or not row.get("away_team"):
            continue
        if lo and not (lo <= date <= hi):
            continue
        if model_version and row.get("model_version") != model_version:
            continue
        # Rule 1: a row logged after the game date is not a prediction.
        run_date = row.get("run_date") or ""
        if run_date > date:
            continue

        key = _game_key(date, row["home_team"], row["away_team"])
        prev = best.get(key)
        if prev is None or (row.get("timestamp_utc") or "") > (prev.get("timestamp_utc") or ""):
            best[key] = row
    return best


def load_market(snapshot_dir: Path = SNAPSHOT_DIR) -> dict:
    """Read every snapshot and return {game_key: entry} holding the latest
    quote taken strictly before that game's commence time (the closing line).

    Team names are mapped to NHL abbreviations and the game date is derived
    from commence time exactly as main.py derives it, so the keys line up with
    the prediction log."""
    if not snapshot_dir.exists():
        return {}

    closing = {}
    for path in sorted(snapshot_dir.glob("*.json")):
        try:
            snap = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        taken_at = snap.get("timestamp_utc")
        if not taken_at:
            continue
        taken = datetime.fromisoformat(taken_at)

        for g in snap.get("games", []):
            commence_raw = g.get("commence_time")
            if not commence_raw:
                continue
            commence = datetime.fromisoformat(str(commence_raw).replace("Z", "+00:00"))
            # Rule 2: the benchmark never sees a price set after puck drop.
            if taken >= commence:
                continue

            key = _game_key(
                commence.astimezone(EST).strftime("%Y-%m-%d"),
                team_name_to_abbrev(g.get("home_team", "")),
                team_name_to_abbrev(g.get("away_team", "")),
            )
            prev = closing.get(key)
            if prev is None or taken > prev["_taken"]:
                closing[key] = {**g, "_taken": taken, "_snapshot": path.name}
    return closing


def fetch_actuals(dates, include_playoffs: bool = False) -> tuple:
    """({game_key: {home_win, total_goals}}, [failed_dates]) for every final
    game on `dates`.

    A date whose fetch fails (the NHL API rate-limits aggressively) is
    collected and returned rather than aborting the whole report — but it is
    never swallowed: the caller warns on stderr and the count is printed in
    the report header, because a scorecard silently missing a week of games
    is worse than no scorecard."""
    actuals, failed = {}, []
    for date in sorted(dates):
        try:
            games = fetch_scores(date)
        except Exception as e:
            print(f"  ⚠️  Could not fetch results for {date}: {e}", file=sys.stderr)
            failed.append(date)
            continue
        for g in games:
            if g.get("game_state") not in ("FINAL", "OFF"):
                continue
            if not include_playoffs and g.get("game_type") != REGULAR_SEASON:
                continue
            hs, as_ = g.get("home_score"), g.get("away_score")
            if hs is None or as_ is None:
                continue
            key = _game_key(date, g.get("home_team", ""), g.get("away_team", ""))
            actuals[key] = {
                "home_win": int(hs > as_),
                "total_goals": int(hs) + int(as_),
            }
    return actuals, failed


# --------------------------------------------------------------------------- #
# Scoring                                                                      #
# --------------------------------------------------------------------------- #
def build_rows(predictions: dict, actuals: dict, market: dict) -> tuple:
    """Join the three sources. Returns (scored, pending) where `scored` holds
    one dict per game that has both a pre-game prediction and a final result."""
    scored, pending = [], []
    for key, pred in sorted(predictions.items()):
        actual = actuals.get(key)
        if actual is None:
            pending.append(key)
            continue
        mkt = market.get(key)
        scored.append({
            "date": key[0],
            "home_team": key[1],
            "away_team": key[2],
            "model_version": pred.get("model_version"),
            "model_home_win_prob": float(pred["home_win_prob"]),
            "model_expected_total": (
                float(pred["expected_total"]) if pred.get("expected_total") is not None else None),
            "market_home_win_prob": (
                float(mkt["home_win_prob"]) if mkt and mkt.get("home_win_prob") is not None else None),
            "market_total_line": (
                float(mkt["total_line"]) if mkt and mkt.get("total_line") is not None else None),
            "market_snapshot": mkt["_snapshot"] if mkt else None,
            "home_win": actual["home_win"],
            "total_goals": actual["total_goals"],
        })
    return scored, pending


def win_metrics(probs, outcomes, n_bins: int = 10) -> dict:
    """Proper scoring rules for P(home win). Empty input returns an empty dict
    rather than a NaN-filled one that reads like a real result."""
    if not len(probs):
        return {}
    p = np.asarray(probs, dtype=float)
    y = np.asarray(outcomes, dtype=int)
    out = {
        "n": int(len(p)),
        "accuracy": float(accuracy_score(y, p > 0.5)),
        "brier": float(brier_score_loss(y, p)),
        "ece": float(expected_calibration_error(p, y, n_bins)),
    }
    # log_loss needs both classes present to be meaningful; early in a season
    # a handful of games can be all-home-wins.
    out["log_loss"] = float(log_loss(y, p, labels=[0, 1])) if len(set(y.tolist())) > 1 else float("nan")
    return out


def totals_metrics(predicted, actual) -> dict:
    if not len(predicted):
        return {}
    pred = np.asarray(predicted, dtype=float)
    act = np.asarray(actual, dtype=float)
    return {
        "n": int(len(pred)),
        "rmse": float(np.sqrt(np.mean((pred - act) ** 2))),
        "mae": float(np.mean(np.abs(pred - act))),
        "poisson_nll": poisson_nll(act, pred),
    }


def compute_scorecard(scored: list, n_bins: int = 10) -> dict:
    """Model metrics on every scored game, plus a model-vs-market table
    restricted to the games where both had a pre-game number (rule 3)."""
    model_p = [r["model_home_win_prob"] for r in scored]
    y = [r["home_win"] for r in scored]

    head_to_head = [r for r in scored if r["market_home_win_prob"] is not None]
    h2h_y = [r["home_win"] for r in head_to_head]

    totals_rows = [r for r in scored if r["model_expected_total"] is not None]
    totals_h2h = [r for r in totals_rows if r["market_total_line"] is not None]

    return {
        "n_scored": len(scored),
        "model_versions": dict(Counter(r["model_version"] for r in scored)),
        "date_range": [scored[0]["date"], scored[-1]["date"]] if scored else None,
        "win": {
            "model_all_games": win_metrics(model_p, y, n_bins),
            "head_to_head": {
                "n": len(head_to_head),
                "model": win_metrics([r["model_home_win_prob"] for r in head_to_head], h2h_y, n_bins),
                "market": win_metrics([r["market_home_win_prob"] for r in head_to_head], h2h_y, n_bins),
            },
        },
        "totals": {
            "model_all_games": totals_metrics(
                [r["model_expected_total"] for r in totals_rows],
                [r["total_goals"] for r in totals_rows]),
            "head_to_head": {
                "n": len(totals_h2h),
                "model": totals_metrics(
                    [r["model_expected_total"] for r in totals_h2h],
                    [r["total_goals"] for r in totals_h2h]),
                # The market's total line is a betting line, not a mean
                # forecast; scored here as a point prediction, which is the
                # only apples-to-apples use of it.
                "market_line": totals_metrics(
                    [r["market_total_line"] for r in totals_h2h],
                    [r["total_goals"] for r in totals_h2h]),
            },
        },
        "reliability": reliability_table(model_p, y, n_bins) if scored else [],
    }


# --------------------------------------------------------------------------- #
# Report                                                                       #
# --------------------------------------------------------------------------- #
def _fmt(value, spec=".4f") -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "—"
    return format(value, spec)


def print_report(card: dict, pending: int, season: str, failed_dates: list = ()) -> None:
    print("=" * 78)
    print("  SEASON SCORECARD — predictions logged before puck drop, scored after")
    print("=" * 78)
    print(f"  Season: {season}   Games scored: {card['n_scored']}"
          + (f"   Awaiting results: {pending}" if pending else ""))
    if card["date_range"]:
        print(f"  Range:  {card['date_range'][0]} to {card['date_range'][1]}")
    if failed_dates:
        print(f"  ⚠️  INCOMPLETE: results could not be fetched for "
              f"{len(failed_dates)} date(s) — {', '.join(sorted(failed_dates)[:5])}"
              + (" …" if len(failed_dates) > 5 else ""))
        print("      Games on those dates are missing from every number below.")

    versions = card["model_versions"]
    if len(versions) > 1:
        print("  ⚠️  Mixed model versions in this window — these are different "
              "models, not one:")
        for v, n in sorted(versions.items(), key=lambda kv: -kv[1]):
            print(f"        {n:>5} games  {v}")
        print("      Re-run with --model-version to score one of them alone.")
    elif versions:
        print(f"  Model:  {next(iter(versions))}")

    m = card["win"]["model_all_games"]
    print("-" * 78)
    print("  WIN PROBABILITY")
    print(f"{'Source':<34}{'n':>7}{'Accuracy':>10}{'Log loss':>11}{'Brier':>9}{'ECE':>8}")
    print("-" * 78)
    print(f"{'Model (all logged games)':<34}{m['n']:>7}{_fmt(m['accuracy'], '.3f'):>10}"
          f"{_fmt(m['log_loss']):>11}{_fmt(m['brier']):>9}{_fmt(m['ece']):>8}")

    h2h = card["win"]["head_to_head"]
    if h2h["n"]:
        hm, hk = h2h["model"], h2h["market"]
        print(f"{'Model (games w/ market price)':<34}{hm['n']:>7}{_fmt(hm['accuracy'], '.3f'):>10}"
              f"{_fmt(hm['log_loss']):>11}{_fmt(hm['brier']):>9}{_fmt(hm['ece']):>8}")
        print(f"{'Market closing consensus':<34}{hk['n']:>7}{_fmt(hk['accuracy'], '.3f'):>10}"
              f"{_fmt(hk['log_loss']):>11}{_fmt(hk['brier']):>9}{_fmt(hk['ece']):>8}")
        print("-" * 78)
        if not np.isnan(hm.get("log_loss", float("nan"))) and not np.isnan(hk.get("log_loss", float("nan"))):
            gap = hm["log_loss"] - hk["log_loss"]
            if gap < 0:
                print(f"  Model is AHEAD of the market by {abs(gap):.4f} log loss "
                      f"on {h2h['n']} games.")
            else:
                print(f"  Model trails the market by {gap:.4f} log loss on "
                      f"{h2h['n']} games.")
            print("  (The market is the hardest public benchmark there is — "
                  "trailing it is the norm.)")
            # A thin sample is how this project got burned before (README:
            # a 35-bet sample). Say so on the same line as the claim, not in
            # a footnote nobody reads.
            if h2h["n"] < MEANINGFUL_SAMPLE:
                print(f"  ⚠️  {h2h['n']} games is too few to separate two "
                      f"forecasters — a gap this size is noise until roughly")
                print(f"      {MEANINGFUL_SAMPLE}+ games. Provisional, not a result.")
    else:
        print("-" * 78)
        print("  No pre-game market price joined to any scored game yet — the "
              "market column")
        print("  needs snapshots taken before puck drop for these games.")

    t = card["totals"]["model_all_games"]
    if t:
        print("-" * 78)
        print("  EXPECTED TOTAL GOALS")
        print(f"{'Source':<34}{'n':>7}{'RMSE':>11}{'MAE':>9}{'Poisson NLL':>14}")
        print("-" * 78)
        print(f"{'Model (all logged games)':<34}{t['n']:>7}{_fmt(t['rmse']):>11}"
              f"{_fmt(t['mae'], '.3f'):>9}{_fmt(t['poisson_nll']):>14}")
        th2h = card["totals"]["head_to_head"]
        if th2h["n"]:
            tm, tk = th2h["model"], th2h["market_line"]
            print(f"{'Model (games w/ market line)':<34}{tm['n']:>7}{_fmt(tm['rmse']):>11}"
                  f"{_fmt(tm['mae'], '.3f'):>9}{_fmt(tm['poisson_nll']):>14}")
            print(f"{'Market total line':<34}{tk['n']:>7}{_fmt(tk['rmse']):>11}"
                  f"{_fmt(tk['mae'], '.3f'):>9}{_fmt(tk['poisson_nll']):>14}")

    populated = [r for r in card["reliability"] if r["count"]]
    if populated:
        print("-" * 78)
        print("  CALIBRATION — does 60% mean 60%?")
        print(f"{'prob bin':<14}{'n':>7}{'predicted':>12}{'observed':>11}{'gap':>9}")
        print("-" * 78)
        for row in populated:
            gap = row["mean_pred"] - row["frac_pos"]
            label = "[{:.2f},{:.2f})".format(row["lo"], row["hi"])
            print(f"{label:<14}{row['count']:>7}"
                  f"{row['mean_pred']:>12.3f}{row['frac_pos']:>11.3f}{gap:>+9.3f}")
    print("-" * 78)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--season", default=None,
                        help="Season to score, e.g. 20262027 (default: current)")
    parser.add_argument("--all-seasons", action="store_true",
                        help="Score every row in the log regardless of season")
    parser.add_argument("--model-version", default=None,
                        help="Score only rows stamped with this win model version")
    parser.add_argument("--include-playoffs", action="store_true",
                        help="Include playoff games (excluded by default: the "
                             "shipped models are fit on regular season games)")
    parser.add_argument("--bins", type=int, default=10,
                        help="Calibration bin count (default: 10)")
    parser.add_argument("--json", dest="json_path", default=None,
                        help="Also write the scorecard as JSON to this path")
    args = parser.parse_args()

    season = None if args.all_seasons else (args.season or current_season())
    predictions = load_predictions(season=season, model_version=args.model_version)

    if not predictions:
        where = "all seasons" if args.all_seasons else f"season {season}"
        print(f"No pre-game predictions logged for {where} yet "
              f"({PREDICTIONS_LOG.relative_to(BASE)}).")
        print("Nothing to score — this is the expected state until the daily "
              "job starts logging games.")
        return 0

    actuals, failed_dates = fetch_actuals({key[0] for key in predictions},
                                          include_playoffs=args.include_playoffs)
    market = load_market()
    scored, pending = build_rows(predictions, actuals, market)

    if not scored:
        print(f"{len(predictions)} prediction(s) logged, none with a final "
              f"result yet — nothing to score.")
        return 0

    card = compute_scorecard(scored, args.bins)
    print_report(card, len(pending), "all" if args.all_seasons else season, failed_dates)

    if args.json_path:
        out = Path(args.json_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(
            {"generated_utc": datetime.now(timezone.utc).isoformat(),
             "season": "all" if args.all_seasons else season,
             "n_pending": len(pending),
             "failed_result_dates": sorted(failed_dates),
             **card,
             "games": scored},
            indent=2, default=str))
        print(f"\nWrote {out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
