#!/usr/bin/env python3
"""
The closest NHL play-by-play gets to an odd-man rush: a shot seconds after
the shooting team won the puck (a takeaway, or the other side's giveaway)
in the neutral or defensive zone. NHL data never counts who is back, so this
catches every transition off a turnover, odd-man or not; an odd-man rush is
the subset where the defence is short, so its effect should sit above this.

    python nhl_turnover_rush.py

The base model's logit is a fixed offset, so each number is what the event
adds on top of where the shot came from. Empty-net shots are left out.
"""
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
import sys, joblib, numpy as np, pandas as pd
sys.path.insert(0, ".")
from xg_model import predict_xg, MODEL_PATH
from tag_features import logit
from scipy.optimize import minimize
d = pd.read_parquet("data/shots.parquet")
d = d[~d.is_empty_net.astype(bool)]
off = logit(predict_xg(joblib.load(MODEL_PATH), d))
y = d.goal.to_numpy(float)
turn = d.prev_event.isin(["TAKE", "GIVE"]).to_numpy()
zone = d.prev_event_zone.astype(str).to_numpy()
t = d.time_since_last_event.astype(float).to_numpy()
dist = d.distance_from_last_event.astype(float).to_numpy()
def fit(mask):
    X = np.column_stack([np.ones(len(d)), mask.astype(float)])
    nll = lambda b: -(y*(off+X@b) - np.logaddexp(0, off+X@b)).sum()
    b = minimize(nll, np.zeros(2), method="BFGS").x
    p = 1/(1+np.exp(-(off+X@b))); H = (X*(p*(1-p))[:,None]).T@X
    se = np.sqrt(np.diag(np.linalg.inv(H)))
    return b[1], se[1]
print(f"{len(d):,} non-empty-net shots")
rows = []
for name, m in [
    ("turnover in NZ/DZ, shot <= 4 s", turn & np.isin(zone, ["NEU","DEF"]) & (t <= 4)),
    ("turnover in NZ/DZ, shot <= 6 s", turn & np.isin(zone, ["NEU","DEF"]) & (t <= 6)),
    ("turnover in NZ/DZ, shot <= 10 s", turn & np.isin(zone, ["NEU","DEF"]) & (t <= 10)),
    ("  ... <= 6 s and traveled >= 60 ft", turn & np.isin(zone, ["NEU","DEF"]) & (t <= 6) & (dist >= 60)),
    ("turnover in OZ (forecheck), <= 4 s", turn & (zone == "OFF") & (t <= 4)),
    ("any NZ/DZ event, shot <= 4 s (README proxy)", np.isin(zone, ["NEU","DEF"]) & (t <= 4)),
]:
    b, se = fit(m)
    g = y[m].sum()
    print(f"  {name:<44} n={m.sum():>7,} goals={int(g):>6,}  coef {b:+.3f} ± {se:.3f}  odds x{np.exp(b):.2f}")
# stability by season for the main proxy
m = turn & np.isin(zone, ["NEU","DEF"]) & (t <= 6)
print("  by season (NZ/DZ turnover, <= 6 s):", end="")
for s_ in sorted(d.season.unique()):
    k = (d.season == s_).to_numpy()
    X = np.column_stack([np.ones(k.sum()), m[k].astype(float)])
    o, yy = off[k], y[k]
    nll = lambda b: -(yy*(o+X@b) - np.logaddexp(0, o+X@b)).sum()
    b = minimize(nll, np.zeros(2), method="BFGS").x
    print(f" {s_}:{np.exp(b[1]):.2f}", end="")
print()
