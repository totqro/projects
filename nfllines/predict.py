"""
Live predictions for a (season, week): the serving path.

Walks every completed week before the target week with the SAME engine
that built the training table (src/features/build.py), computes features
for the target week's games, applies the frozen win and points models
(served from the coefficients in ml_models/*.json), prints them and
appends them to data/predictions_log.jsonl.

    python predict.py                        # upcoming week of the current season
    python predict.py --season 2026 --week 3

Run it Wednesday evening (logs the Thursday game) and Saturday evening (logs
Sunday and Monday). A game is logged only when its final injury report is
out and it has not kicked off (src/readiness.py); everything else is
printed with the reason it was held back. --force logs regardless, loudly.

Starting QBs come from the nflverse schedule's home_qb_id/away_qb_id; for an
upcoming game those columns are nflverse's expected starter and are
updated as news breaks, so re-running closer to kickoff picks up changes.
Output is coherent by construction (src/models/coherent.py): margin comes from
the win probability, only the total from the points model, so the shipped
probability and shipped points always name the same favourite.

Nothing in this file reads a market column.
"""
import argparse
import json
import os
from datetime import datetime

import numpy as np
import pandas as pd

from src.data import nflverse as nv
from src.features.build import load_inputs, make_engine, attach_targets
from src.models.coherent import coherent_points
from src.models.points_model import ServedPointsModel
from src.models.prediction_log import log_predictions
from src.models.win_model import ServedWinModel, WIN_MODEL_PATH, POINTS_MODEL_PATH
from src.readiness import ET, game_readiness, season_complete_before


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", type=int, default=nv.current_season())
    ap.add_argument("--week", type=int, help="default: the earliest week with an unplayed game")
    ap.add_argument("--no-log", action="store_true")
    ap.add_argument("--force", action="store_true", help="log games the readiness guard holds back")
    ap.add_argument("--features-out", help="write the exact feature rows served (CSV, full precision) for auditing")
    args = ap.parse_args()

    seasons = tuple(range(nv.WARM_START_SEASON, args.season + 1))
    inputs = load_inputs(seasons)
    games = inputs["games"]
    now = datetime.now(ET)
    if args.week is None:
        from src.readiness import kickoff_et
        upcoming = games[(games.season == args.season) & games.home_score.isna()]
        upcoming = upcoming[[kickoff_et(g) > now for _, g in upcoming.iterrows()]]
        if upcoming.empty:
            raise SystemExit("no upcoming games this season")
        args.week = int(upcoming.week.min())
    print(f"season {args.season} week {args.week}  (run at {now:%a %Y-%m-%d %H:%M} ET)")
    missing = season_complete_before(games, inputs["team_games"], args.season, args.week, now)
    if missing:
        msg = f"ratings incomplete, nflverse has not published: {', '.join(missing)}; nothing will be logged"
        print(("::warning::" if os.environ.get("GITHUB_ACTIONS") else "") + msg)
    target = games[(games.season == args.season) & (games.week == args.week)]
    if target.empty:
        raise SystemExit("no games for that season/week in the schedule")

    eng = make_engine(inputs)
    eng.run(games, inputs["team_games"], inputs["qb_games"], context=inputs["context"],
            stop_before=(args.season, args.week), emit=False)
    eng.efficiency.start_week(args.season, args.week)
    eng.injuries.start_week(args.season, args.week, inputs["context"])
    rows = pd.DataFrame([eng.features_for(g) for _, g in target.iterrows()])
    rows = attach_targets(rows, games)
    if args.features_out:
        rows.to_csv(args.features_out, index=False, float_format="%.17g")

    # Frozen models served straight from their JSON coefficients: no feature
    # table, no refit, identical to the fitted models to machine precision.
    wm = ServedWinModel(WIN_MODEL_PATH)
    p = wm.predict_proba(rows)
    total = ServedPointsModel(POINTS_MODEL_PATH).predict(rows).pred_total.to_numpy()
    # One favourite everywhere: margin from the win probability, total from
    # the points model, team points = (total +- margin) / 2.
    pts = coherent_points(p, total, wm.sigma)

    out = []
    print(f"{'game':<20}{'P(home)':>9}{'margin':>8}{'home':>7}{'away':>7}{'total':>7}  status")
    for i, r in rows.iterrows():
        g = target[target.game_id == r.game_id].iloc[0]
        ready, why = game_readiness(g, inputs["context"]["injuries"], now)
        if ready and missing:
            ready, why = False, "earlier results missing (see above)"
        log_it = ready or (args.force and why != "kicked off")
        status = "logged" if (log_it and not args.no_log) else ("ready" if ready else f"held: {why}")
        if log_it and not ready:
            status = f"FORCED ({why})"
        print(f"{r.game_id:<20}{p[i]:>9.3f}{pts['margin'][i]:>8.1f}{pts['home'][i]:>7.1f}{pts['away'][i]:>7.1f}"
              f"{pts['total'][i]:>7.1f}  {status}")
        if not log_it:
            continue
        from src.readiness import kickoff_et
        out.append({"game_id": r.game_id, "season": int(r.season), "week": int(r.week),
                    "home_team": r.home_team, "away_team": r.away_team, "kickoff_et": kickoff_et(g).isoformat(),
                    "home_win_prob": float(p[i]), "expected_margin": float(pts["margin"][i]),
                    "expected_home_points": float(pts["home"][i]),
                    "expected_away_points": float(pts["away"][i]),
                    "expected_total": float(pts["total"][i]),
                    "readiness": why, "forced": bool(log_it and not ready)})
    if not args.no_log:
        n = log_predictions(out)
        print(f"logged {n} new prediction rows")


if __name__ == "__main__":
    main()
