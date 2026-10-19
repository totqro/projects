#!/usr/bin/env python3
"""
Measure the royal-road and rush effects on real games: Stathletes' Big Data
Cup event data, which (unlike any NHL feed) records every completed pass
with where it started and where it was received.

    python bdc_royal_road.py DATA_DIR            # fit and print
    python bdc_royal_road.py DATA_DIR --write    # also store the royal-road
                                                 # fit as the prior in
                                                 # tag_adjustments.json

DATA_DIR holds the Big Data Cup 2021 CSVs (github.com/bigdatacup/
Big-Data-Cup-2021): hackathon_womens.csv (NCAA), hackathon_nwhl.csv and
pxp_womens_oly_2022_v2.csv (2022 Olympics). The men's OHL file the repo used
to carry is gone. All three are women's hockey, so the fit carries its own
intercept: it asks how much a royal-road pass adds on top of where the shot
came from, not what a shot is worth in that league.

A shot is a royal-road shot when the event right before it is a completed
pass by the same team to the shooter, within the clock's resolution (1 s;
the tracker's rule is 0.5 s), from below the circle tops on one side of the
road to a shooter below the circle tops on the other (tag_features.
crosses_royal_road). The base model's logit is a fixed offset, as in
fit_tagged.py.

Two things this data cannot give, checked rather than assumed:
  - odd-man rushes: there is no count of who is back. A carried zone entry
    shortly before the shot is measured as "rush" for reference, but it is a
    broader, weaker thing than an odd-man rush and is not written anywhere.
  - the block factor: every goal is recorded "On Net", so no blocked
    attempt ever scores here.
"""

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from tag_features import ADJUSTMENTS_PATH, crosses_royal_road, load_adjustments, logit
from xg_model import MODEL_PATH, predict_xg
from zone_tagging import geometry

PASS_WINDOW_S = 1      # clock is whole seconds; the tracker's rule is 0.5 s
REBOUND_S = 3
RUSH_WINDOW_S = 5      # carried zone entry this close before the shot
SHOT_TYPES = {"Snapshot": "WRIST", "Wristshot": "WRIST", "Slapshot": "SLAP",
              "Deflection": "DEFL", "Wrap Around": "WRAP"}   # Fan: dropped
SITUATIONS = {(5, 5): "EV_5v5", (4, 4): "EV_4v4", (3, 3): "EV_3v3",
              (5, 4): "PP_5v4", (5, 3): "PP_5v3", (4, 3): "PP_4v3",
              (4, 5): "SH_4v5", (3, 5): "SH_OTHER", (3, 4): "SH_OTHER"}


def load_2021(path: Path) -> pd.DataFrame:
    d = pd.read_csv(path)
    mm, ss = d["Clock"].str.split(":", expand=True).astype(int).T.values
    home = d["Team"] == d["Home Team"]
    goal = d["Event"] == "Goal"
    return pd.DataFrame({
        "game": d["game_date"] + " " + d["Home Team"] + " " + d["Away Team"],
        "period": d["Period"], "sec": mm * 60 + ss, "team": d["Team"],
        "player": d["Player"], "player2": d["Player 2"],
        "event": np.where(goal, "Shot", d["Event"]), "goal": goal.astype(int),
        "ok": ~d["Event"].isin(["Incomplete Play"]),
        "x": d["X Coordinate"], "y": d["Y Coordinate"],
        "x2": d["X Coordinate 2"], "y2": d["Y Coordinate 2"],
        "shot_type": d["Detail 1"], "dest": d["Detail 2"],
        "entry": d["Detail 1"],
        "sk_for": np.where(home, d["Home Team Skaters"], d["Away Team Skaters"]),
        "sk_against": np.where(home, d["Away Team Skaters"], d["Home Team Skaters"]),
    })


def load_oly(path: Path) -> pd.DataFrame:
    d = pd.read_csv(path)
    sk = d["situation_type"].str.extract(r"(\d) on (\d)").astype(float)
    shot = d["event"] == "Shot"
    return pd.DataFrame({
        "game": d["game_date"] + " " + d["team_name"].where(d["venue"] == "home", d["opp_team_name"]),
        "period": d["period"], "sec": d["clock_seconds"], "team": d["team_name"],
        "player": d["player_name"], "player2": d["player_name_2"],
        "event": d["event"], "goal": (shot & (d["event_successful"] == "t")).astype(int),
        "ok": d["event_successful"] == "t",
        "x": d["x_coord"], "y": d["y_coord"], "x2": d["x_coord_2"], "y2": d["y_coord_2"],
        "shot_type": d["event_type"], "dest": d["event_detail_1"],
        "entry": d["event_type"], "sk_for": sk[0], "sk_against": sk[1],
    })


def shots_with_context(ev: pd.DataFrame, source: str) -> pd.DataFrame:
    """One row per unblocked shot, with the base-model features and tags."""
    rows = []
    # Coordinates are from the eventing team's side, attacking x = 200.
    # Our frame: x - 100 (net at 89), y - 42.5.
    for (_, _), g in ev.groupby(["game", "period"], sort=False):
        g = g.reset_index(drop=True)
        for i in np.flatnonzero(g.event.to_numpy() == "Shot"):
            s = g.iloc[i]
            if s.dest == "Blocked" or s.shot_type not in SHOT_TYPES:
                continue
            sit = SITUATIONS.get((s.sk_for, s.sk_against))
            if sit is None:
                continue
            X, Y = s.x - 100, s.y - 42.5
            prev = g.iloc[i - 1] if i else None
            assisted = (prev is not None and prev.event == "Play" and prev.ok
                        and prev.team == s.team and prev.player2 == s.player
                        and 0 <= prev.sec - s.sec <= PASS_WINDOW_S)
            rr = bool(assisted and crosses_royal_road(prev.x - 100, prev.y - 42.5, X, Y))
            before = g.iloc[max(0, i - 12):i]
            recent = before[before.sec - s.sec <= RUSH_WINDOW_S]
            rebound = bool(((before.event == "Shot") & (before.team == s.team)
                            & (before.sec - s.sec <= REBOUND_S)).any())
            # Rush: a carried entry by this team with no opponent event since.
            rush = False
            for _, e in recent[::-1].iterrows():
                if e.team != s.team:
                    break
                if e.event == "Zone Entry" and e.entry == "Carried":
                    rush = True
                    break
            d, a = geometry(X, Y)
            rows.append({"source": source, "goal": s.goal, "distance": float(d),
                         "angle_from_net": float(a), "shot_type": SHOT_TYPES[s.shot_type],
                         "is_rebound": int(rebound), "situation": sit,
                         "assisted": int(assisted), "royal_road": int(rr), "rush": int(rush)})
    return pd.DataFrame(rows)


def fit(offset, X, y):
    """Plain maximum likelihood, logit offset fixed. Returns coef, sd."""
    def nll(b):
        z = offset + X @ b
        return -(y * z - np.logaddexp(0, z)).sum()

    def grad(b):
        return -X.T @ (y - 1 / (1 + np.exp(-(offset + X @ b))))

    b = minimize(nll, np.zeros(X.shape[1]), jac=grad, method="BFGS").x
    p = 1 / (1 + np.exp(-(offset + X @ b)))
    hess = (X * (p * (1 - p))[:, None]).T @ X
    return b, np.sqrt(np.diag(np.linalg.inv(hess)))


def report(name, df, offset, terms):
    X = np.column_stack([np.ones(len(df))] + [df[t].to_numpy(float) for t in terms])
    b, se = fit(offset, X, df.goal.to_numpy(float))
    print(f"\n  {name}")
    print(f"    {'term':<12}{'shots':>7}{'goals':>7}{'coef':>8}{'± sd':>7}{'odds x':>8}   95% range")
    for i, t in enumerate(["league"] + terms):
        m = np.ones(len(df), bool) if t == "league" else df[t].to_numpy() == 1
        lo, hi = np.exp(b[i] - 1.96 * se[i]), np.exp(b[i] + 1.96 * se[i])
        print(f"    {t:<12}{int(m.sum()):>7}{int(df.goal[m].sum()):>7}{b[i]:>+8.3f}"
              f"{se[i]:>7.3f}{np.exp(b[i]):>8.2f}   x{lo:.2f} to x{hi:.2f}")
    return dict(zip(["league"] + terms, zip(b, se)))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data_dir", type=Path)
    ap.add_argument("--write", action="store_true",
                    help="store the royal-road estimate as the cross_ice prior")
    args = ap.parse_args()

    parts = []
    for name, loader in [("hackathon_womens.csv", load_2021), ("hackathon_nwhl.csv", load_2021),
                         ("pxp_womens_oly_2022_v2.csv", load_oly)]:
        path = args.data_dir / name
        if path.exists():
            parts.append(shots_with_context(loader(path), name.split(".")[0]))
    if not parts:
        sys.exit(f"No Big Data Cup files in {args.data_dir}")
    df = pd.concat(parts, ignore_index=True)

    offset = logit(predict_xg(joblib.load(MODEL_PATH), df))
    print(f"{len(df)} unblocked shots, {int(df.goal.sum())} goals, "
          f"{df.assisted.sum()} straight off a pass, {df.royal_road.sum()} royal-road")
    print("  by source: " + ", ".join(f"{k} {len(g)}/{int(g.goal.sum())}"
                                      for k, g in df.groupby("source")))
    print(f"  base model (NHL-fit) xG {(1/(1+np.exp(-offset))).sum():.1f} "
          f"vs {int(df.goal.sum())} goals")

    main_fit = report("royal road, with league shift", df, offset, ["royal_road"])
    report("royal road vs any pass-then-shot", df, offset, ["assisted", "royal_road"])
    report("rush (carried entry <= 5 s before; NOT odd-man) with royal road",
           df, offset, ["royal_road", "rush"])

    if args.write:
        b, se = main_fit["royal_road"]
        adj = load_adjustments()
        adj["cross_ice"]["prior"] = round(float(b), 4)
        adj["cross_ice"]["prior_sd"] = round(float(se), 4)
        adj["cross_ice"]["coef"] = round(float(b), 4)
        adj["cross_ice"]["prior_source"] = (
            f"Big Data Cup 2021 women's NCAA/NWHL/Olympic events: "
            f"{int(df.royal_road.sum())} royal-road shots, "
            f"{int(df.goal[df.royal_road == 1].sum())} goals, of {len(df)} unblocked")
        ADJUSTMENTS_PATH.write_text(json.dumps(adj, indent=2) + "\n")
        print(f"\nWrote cross_ice prior {b:+.3f} ± {se:.3f} to {ADJUSTMENTS_PATH.name}")


if __name__ == "__main__":
    main()
