#!/usr/bin/env python3
"""
Per-game team xG from High Slot's model, for the nhllines win model.

    python export_team_game_xg.py                        # 2017-18 .. season in progress
    python export_team_game_xg.py --first 2022 --out PATH

nhllines builds its xG features from one {game_id: {team: totals}} shape
(src/data/moneypuck_data.py). This writes High Slot's version of it, so the
win model can be fitted and gated on High Slot xG instead of MoneyPuck's.

Every completed season is scored walk-forward: season S by a model trained on
2015 .. S-2 and calibrated on S-1, so no season's xG has seen its own goals.
The production model would not do: it trains on every complete season but
the last, so its xG for those seasons is in-sample and would flatter any
win model fitted on them. The season in progress is scored by the production
model, the one behind the site's games.json, so it matches what nhllines can
read at serving time.

Totals per team and game, regular season, unblocked attempts only:
    xgf, xga            all situations
    xgf_adj, xga_adj    5v5 with the score within one goal (MoneyPuck stand-in)
    xgf5, xga5          5v5, any score (what games.json publishes as hxg5/axg5)
    hd_xgf, hd_xga      shots with xG >= 0.08
"""

import argparse
import json
import sys
from pathlib import Path

import joblib
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from nhl_sheets import current_season  # noqa: E402
from src.models.nhl_xg import FEATURE_SETS, XGModel  # noqa: E402

DATA = ROOT / "data" / "nhl_shots.parquet"
MODEL_PATH = ROOT / "data" / "nhl_xg_model.joblib"
DEFAULT_OUT = ROOT.parents[1] / "nhllines" / "data" / "highslot_team_game_xg.json"

HIGH_DANGER_XG = 0.08  # nhllines' HIGH_DANGER_XG_THRESHOLD


def walk_forward_xg(df, season):
    """xG for `season`'s shots from a model that never saw that season."""
    train = df[df.season <= season - 2]
    valid = df[df.season == season - 1]
    num, cat = FEATURE_SETS["full"]
    m = XGModel(num, cat).fit(train, valid)
    print(f"  {season}: trained {train.season.min()}-{season - 2}, calibrated {season - 1}, "
          f"{m.clf.max_iter} trees", flush=True)
    return m.predict(df[df.season == season])


def aggregate(shots):
    """{game_id: {team: totals}} from scored, unblocked, regular-season shots."""
    s = shots.assign(
        defending=shots.home_team.where(shots.team == shots.away_team, shots.away_team),
        close5=(shots.situation == "EV_5v5") & (shots.score_differential.abs() <= 1),
        ev5=shots.situation == "EV_5v5",
        hd=shots.xg >= HIGH_DANGER_XG,
    )
    out = {}
    for gid, g in s.groupby("game_id"):
        home, away = g.home_team.iat[0], g.away_team.iat[0]
        teams = {}
        for team in (home, away):
            f, a = g[g.team == team], g[g.defending == team]
            teams[team] = {
                "is_home": team == home,
                "xgf": round(f.xg.sum(), 4), "xga": round(a.xg.sum(), 4),
                "xgf_adj": round(f.xg[f.close5].sum(), 4), "xga_adj": round(a.xg[a.close5].sum(), 4),
                "xgf5": round(f.xg[f.ev5].sum(), 4), "xga5": round(a.xg[a.ev5].sum(), 4),
                "hd_xgf": round(f.xg[f.hd].sum(), 4), "hd_xga": round(a.xg[a.hd].sum(), 4),
            }
        out[str(int(gid))] = teams
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--first", type=int, default=2017,
                    help="first season (start year); 2017 is the first with two earlier seasons to train on")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    a = ap.parse_args()

    df = pd.read_parquet(DATA)
    df = df[df.event != "BLOCK"].reset_index(drop=True)
    live = current_season()
    seasons = [s for s in sorted(df.season.unique()) if s >= a.first]

    games, provenance = {}, {}
    for season in seasons:
        part = df[(df.season == season) & (df.is_playoff == 0)].copy()
        if season == live:
            part["xg"] = joblib.load(MODEL_PATH).predict(part)
            provenance[str(season)] = "production model (nhl_xg_model.joblib)"
            print(f"  {season}: production model, season in progress", flush=True)
        else:
            xg = pd.Series(walk_forward_xg(df, season), index=df.index[df.season == season])
            part["xg"] = xg.loc[part.index]
            provenance[str(season)] = f"walk-forward: train 2015-{season - 2}, calibrate {season - 1}"
        agg = aggregate(part)
        print(f"  {season}: {len(agg)} games, xG/goals {part.xg.sum() / part.goal.sum():.4f}", flush=True)
        games.update(agg)

    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps({"provenance": provenance, "high_danger_xg": HIGH_DANGER_XG,
                                 "games": games}, separators=(",", ":")))
    print(f"wrote {a.out} ({len(games)} games)")


if __name__ == "__main__":
    main()
