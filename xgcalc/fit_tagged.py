#!/usr/bin/env python3
"""
Refit the rush and cross-ice coefficients on hand-tagged games.

    python fit_tagged.py ~/Desktop/uoft\\ hockey          # every *_shots.csv under it
    python fit_tagged.py a.csv b.csv --write              # also update tag_adjustments.json

The five-feature model's logit is held fixed as an offset, so the fit only
asks: given where the shot came from, what it was and the strength state,
how much more often do odd-man-rush and cross-ice shots go in? That is two
numbers from a few hundred shots, so each is shrunk toward its prior
(a Gaussian on the coefficient, tag_adjustments.json) and moves only as far
as the goals justify. With a handful of games expect it to barely move.

Only games tagged with the Rush and CrossIce columns are used. A chart from
before the tracker had them would read as "no rushes, no cross-ice passes"
and drag both coefficients down.

Blocked attempts are left out of that fit: a blocked shot is never a goal.
block_factor is measured separately, from games tagged with OffDefender
(h in the tracker): of the attempts that hit a defender in the lane, the
blocks plus the goals that went in off one, how many went in against what
the model would have given them unblocked:

    block_factor = goals off a defender / (base xG of those attempts)

shrunk toward the current value with two pseudo-goals' weight, since goals
off a defender are rare (a season to see a few dozen).
"""

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from score_tagged import load_tagged
from tag_features import ADJUSTMENTS_PATH, load_adjustments, logit
from xg_model import MODEL_PATH, predict_xg

TERMS = ["rush", "cross_ice"]
BLOCK_PSEUDO_GOALS = 2.0


def find_csvs(paths):
    out = []
    for p in paths:
        p = Path(p).expanduser()
        out += sorted(p.rglob("*_shots*.csv")) if p.is_dir() else [p]
    return out


def tagged_games(paths):
    import pandas as pd
    frames, skipped = [], []
    for path in find_csvs(paths):
        head = pd.read_csv(path, nrows=0).columns.str.strip().str.lower()
        if not {"rush", "crossice"} <= set(head):
            skipped.append(path.name)
            continue
        df = load_tagged(path)
        df["game"] = path.stem
        frames.append(df[df.scored])
    if not frames:
        return None, skipped
    return pd.concat(frames, ignore_index=True), skipped


def block_games(paths):
    import pandas as pd
    frames = []
    for path in find_csvs(paths):
        head = pd.read_csv(path, nrows=0).columns.str.strip().str.lower()
        if "offdefender" in head:
            df = load_tagged(path)
            frames.append(df[df.blocked | ((df.goal == 1) & (df.off_defender == 1))])
    return pd.concat(frames, ignore_index=True) if frames else None


def fit_block_factor(model, df, current):
    """Goals off a defender per unit of unblocked xG among lane-hit attempts,
    shrunk toward `current` (gamma-Poisson, BLOCK_PSEUDO_GOALS of weight)."""
    expected = predict_xg(model, df).sum()
    goals = int(df.goal.sum())
    a, rate = BLOCK_PSEUDO_GOALS, BLOCK_PSEUDO_GOALS / current
    est = (goals + a) / (expected + rate)
    sd = np.sqrt(goals + a) / (expected + rate)
    return goals, expected, est, sd


def fit(offset, X, y, prior, sd):
    """MAP logistic regression with a fixed offset and Gaussian priors."""
    def nll(b):
        z = offset + X @ b
        ll = y * z - np.logaddexp(0, z)
        return -ll.sum() + (((b - prior) / sd) ** 2).sum() / 2

    def grad(b):
        p = 1 / (1 + np.exp(-(offset + X @ b)))
        return -X.T @ (y - p) + (b - prior) / sd ** 2

    res = minimize(nll, prior.copy(), jac=grad, method="BFGS")
    p = 1 / (1 + np.exp(-(offset + X @ res.x)))
    hess = (X * (p * (1 - p))[:, None]).T @ X + np.diag(1 / sd ** 2)
    return res.x, np.sqrt(np.diag(np.linalg.inv(hess)))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="tagged CSVs, or folders of them")
    ap.add_argument("--write", action="store_true",
                    help="store the fitted coefficients in tag_adjustments.json")
    args = ap.parse_args()

    adj = load_adjustments()
    model = joblib.load(MODEL_PATH)
    blocks = block_games(args.paths)
    if blocks is not None and len(blocks):
        k, e, bf, bsd = fit_block_factor(model, blocks, adj["block_factor"])
        print(f"Block factor: {int(blocks.blocked.sum())} blocks + {k} goals off a defender, "
              f"{e:.2f} unblocked xG -> {bf:.3f} ± {bsd:.3f} (now {adj['block_factor']})")
        if args.write:
            adj["block_factor"] = round(float(bf), 4)
            adj["block_fit"] = {"blocks": int(blocks.blocked.sum()), "goals_off_defender": k,
                                "unblocked_xg": round(float(e), 3), "sd": round(float(bsd), 4)}
    else:
        print("Block factor: no games tagged with OffDefender yet (h in the tracker); "
              f"staying at {adj['block_factor']}.")
    df, skipped = tagged_games(args.paths)
    if skipped:
        print(f"Skipped {len(skipped)} file(s) without Rush/CrossIce columns: "
              + ", ".join(skipped))
    if df is None:
        if args.write:
            ADJUSTMENTS_PATH.write_text(json.dumps(adj, indent=2) + "\n")
        sys.exit("No tagged games with Rush and CrossIce columns yet. Tag a game "
                 "with the tracker (f = rush, p = cross-ice), export, and rerun.")

    offset = logit(predict_xg(model, df))
    X = df[TERMS].to_numpy(float)
    y = df.goal.to_numpy(float)
    prior = np.array([adj[t]["prior"] for t in TERMS])
    sd = np.array([adj[t]["prior_sd"] for t in TERMS])

    print(f"\n{df.game.nunique()} game(s), {len(df)} unblocked attempts, "
          f"{int(y.sum())} goals")
    base = 1 / (1 + np.exp(-offset))
    print(f"base model alone: {base.sum():.2f} xG")

    b, se = fit(offset, X, y, prior, sd)
    print(f"\n  {'term':<11}{'shots':>6}{'goals':>6}{'base xG':>9}"
          f"{'prior':>8}{'fit':>8}{'± sd':>7}{'odds x':>8}")
    for i, t in enumerate(TERMS):
        m = X[:, i] == 1
        print(f"  {t:<11}{int(m.sum()):>6}{int(y[m].sum()):>6}{base[m].sum():>9.2f}"
              f"{prior[i]:>+8.2f}{b[i]:>+8.2f}{se[i]:>7.2f}{np.exp(b[i]):>8.2f}")
        if m.sum() < 30:
            print(f"    only {int(m.sum())} {t} shots: the prior is doing most of the work")

    adjusted = 1 / (1 + np.exp(-(offset + X @ b)))
    print(f"\n  sum(xG)/goals  base {base.sum()/max(y.sum(),1):.3f}"
          f"   with tagged layer {adjusted.sum()/max(y.sum(),1):.3f}")

    if args.write:
        for i, t in enumerate(TERMS):
            adj[t]["coef"] = round(float(b[i]), 4)
            adj[t]["fit"] = {"games": int(df.game.nunique()), "shots": int(X[:, i].sum()),
                             "goals": int(y[X[:, i] == 1].sum()), "sd": round(float(se[i]), 4)}
        ADJUSTMENTS_PATH.write_text(json.dumps(adj, indent=2) + "\n")
        print(f"\nWrote {ADJUSTMENTS_PATH.name}. Run export_model_web.py to ship it.")


if __name__ == "__main__":
    main()
