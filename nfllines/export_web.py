"""
Web export for lknox.web.app/nfllines.
======================================
Writes the two JSON files the dashboard reads:

* data/latest_analysis.json: the current week (the earliest week with a game
  not yet final). Every game appears: logged ones with the model's last
  pre-kickoff prediction, not-yet-logged ones with when the prediction will
  post, finished ones with the score.
* data/performance.json: the season scorecard, with the same rules as
  scorecard.py (only pre-kickoff rows count, last pre-kickoff row wins),
  plus per-week numbers and the one-time 2024-2025 test from the README.

The market numbers (de-vigged moneyline, spread, total) are read here for
display and scoring only, never as a feature, exactly as in scorecard.py.

    python export_web.py                 # current season
    python export_web.py --season 2026
"""
import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from scorecard import load_log, load_results, pick_prediction, MIN_GAMES_FOR_VERDICT
from src.data.nflverse import current_season
from src.models.metrics import log_loss, brier
from src.readiness import report_due_et

OUT_DIR = Path(__file__).resolve().parent / "data"

# The one-time 2024-2025 test (README, "Honest results"). Scored once by
# evaluate_test.py and never re-run, so it is a constant here.
TEST_SET = {
    "seasons": "2024-2025",
    "n": 569,
    "rows": [
        {"name": "Vegas (odds at kickoff)", "log_loss": 0.5981, "brier": 0.2059, "accuracy": 0.684},
        {"name": "This model", "log_loss": 0.6119, "brier": 0.2117, "accuracy": 0.687, "model": True},
        {"name": "Simple team ratings (Elo)", "log_loss": 0.6224, "brier": 0.2164, "accuracy": 0.654},
    ],
}


def _f(x, nd=4):
    """JSON-safe float (NaN -> None)."""
    if x is None:
        return None
    x = float(x)
    return None if math.isnan(x) else round(x, nd)


def last_pre_kickoff(log: pd.DataFrame, res: pd.DataFrame) -> pd.DataFrame:
    log = log[log.game_id.isin(res.index)].copy()
    log["kickoff"] = log.game_id.map(res.kickoff)
    pre = log[log.ts < pd.to_datetime(log.kickoff, utc=True)]
    return pick_prediction(pre)


def win_block(y, p):
    return {"n": int(len(y)), "log_loss": _f(log_loss(y, p)), "brier": _f(brier(y, p)),
            "correct": int(((p > .5) == (y == 1)).sum()), "accuracy": _f(np.mean((p > .5) == (y == 1)))}


def scored_games(last: pd.DataFrame, res: pd.DataFrame) -> pd.DataFrame:
    final = res.loc[last.index, "home_score"].notna().to_numpy()
    d = last[final].copy()
    r = res.loc[d.index]
    d["hs"], d["as_"] = r.home_score, r.away_score
    d["margin"], d["total"] = d.hs - d.as_, d.hs + d.as_
    d["p_mkt"], d["spread"], d["tot_line"] = r.p_market, r.spread_line, r.total_line
    return d


def summary(d: pd.DataFrame) -> dict:
    w = d[d.margin != 0]
    if w.empty:
        return {"n": 0}
    y = (w.margin > 0).astype(int).to_numpy()
    pm = w.home_win_prob.to_numpy()
    has_mkt = w.p_mkt.notna().to_numpy()
    out = {"n": int(len(w)), "ties": int((d.margin == 0).sum()),
           "model": win_block(y, pm),
           "coin_flip": win_block(y, np.full(len(w), 0.5)),
           "margin_mae": _f(np.mean(np.abs(d.margin - d.expected_margin)), 2),
           "total_mae": _f(np.mean(np.abs(d.total - d.expected_total)), 2),
           "backups": int((d.quality == "backup").sum())}
    if has_mkt.any():
        out["market"] = win_block(y[has_mkt], w.p_mkt.to_numpy()[has_mkt])
        out["model_same_games"] = win_block(y[has_mkt], pm[has_mkt])
        out["favourite_agreement"] = _f(np.mean((pm[has_mkt] > .5) == (w.p_mkt.to_numpy()[has_mkt] > .5)), 3)
    if d.spread.notna().any():
        out["market_margin_mae"] = _f(np.nanmean(np.abs(d.margin - d.spread)), 2)
    if d.tot_line.notna().any():
        out["market_total_mae"] = _f(np.nanmean(np.abs(d.total - d.tot_line)), 2)
    return out


def game_entry(gid, g, row, now) -> dict:
    """One game of the current week, as the dashboard card renders it."""
    e = {"game_id": gid, "week": int(g.week), "away": g.away_team, "home": g.home_team,
         "kickoff": g.kickoff.isoformat(), "market_home_prob": _f(g.p_market, 3)}
    if row is not None:
        e.update({"home_win_prob": _f(row.home_win_prob), "expected_margin": _f(row.expected_margin, 1),
                  "expected_home_points": _f(row.expected_home_points, 1),
                  "expected_away_points": _f(row.expected_away_points, 1),
                  "expected_total": _f(row.expected_total, 1), "logged_at": row.ts.isoformat(),
                  "backup": row.quality == "backup"})
    if pd.notna(g.home_score):
        e["status"] = "final"
        e["home_score"], e["away_score"] = int(g.home_score), int(g.away_score)
        if row is not None and g.home_score != g.away_score:
            e["correct"] = bool((row.home_win_prob > .5) == (g.home_score > g.away_score))
    elif row is not None:
        e["status"] = "in_progress" if now >= g.kickoff else "logged"
    elif now >= g.kickoff:
        e["status"] = "missed"          # kicked off without a pre-kickoff prediction
    else:
        e["status"] = "pending"
        e["report_due"] = report_due_et(g).isoformat()
    return e


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", type=int, default=current_season())
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    res = load_results(args.season)
    log = load_log()
    log = log[log.season == args.season]
    last = last_pre_kickoff(log, res)

    # ---- current week --------------------------------------------------- #
    open_weeks = res[res.home_score.isna()].week
    week = int(open_weeks.min()) if len(open_weeks) else int(res.week.max())
    wk = res[res.week == week].sort_values(["kickoff", "game_id"])
    games = [game_entry(gid, g, last.loc[gid] if gid in last.index else None, now)
             for gid, g in wk.iterrows()]
    latest = {"timestamp": now.isoformat(), "season": args.season, "week": week,
              "games_analyzed": games,
              "logged": sum(1 for g in games if "home_win_prob" in g),
              "recommendations": []}       # no picks or stakes: not a betting tool

    # ---- performance ---------------------------------------------------- #
    d = scored_games(last, res).sort_values("kickoff")
    weeks = []
    for w_, dw in d.groupby("week"):
        s = summary(dw)
        if s.get("n"):
            weeks.append({"week": int(w_), **s})
    results = []
    for gid, r in d.sort_values("kickoff", ascending=False).iterrows():
        pick_home = r.home_win_prob > .5
        results.append({
            "game_id": gid, "week": int(r.week), "kickoff": r.kickoff.isoformat(),
            "away": r.away_team, "home": r.home_team,
            "away_score": int(r.as_), "home_score": int(r.hs),
            "pick": r.home_team if pick_home else r.away_team,
            "pick_prob": _f(max(r.home_win_prob, 1 - r.home_win_prob), 3),
            "market_pick": (None if pd.isna(r.p_mkt) else (r.home_team if r.p_mkt > .5 else r.away_team)),
            "market_pick_prob": (None if pd.isna(r.p_mkt) else _f(max(r.p_mkt, 1 - r.p_mkt), 3)),
            "correct": None if r.margin == 0 else bool(pick_home == (r.margin > 0)),
            "market_correct": None if (r.margin == 0 or pd.isna(r.p_mkt)) else bool((r.p_mkt > .5) == (r.margin > 0)),
            "expected_margin": _f(r.expected_margin, 1), "margin": int(r.margin),
            "expected_total": _f(r.expected_total, 1), "total": int(r.total),
            "backup": r.quality == "backup",
        })
    perf = {"timestamp": now.isoformat(), "season": args.season,
            "min_games_for_verdict": MIN_GAMES_FOR_VERDICT,
            "season_summary": summary(d) if len(d) else {"n": 0},
            "weeks": weeks, "results": results, "test_set": TEST_SET}

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, obj in (("latest_analysis.json", latest), ("performance.json", perf)):
        (OUT_DIR / name).write_text(json.dumps(obj, indent=1) + "\n")
    print(f"week {week}: {latest['logged']}/{len(games)} games logged; "
          f"season scored {perf['season_summary'].get('n', 0)} games -> {OUT_DIR}")


if __name__ == "__main__":
    main()
