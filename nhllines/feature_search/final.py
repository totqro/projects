"""Locked test: score finalist feature sets on 2024-25 and 2025-26, once.
Walk-forward: 2024-25 is predicted by a fit on 2015-16..2023-24; 2025-26 by a
fit on 2015-16..2024-25. Paired bootstrap vs Elo and vs the shipped 44.
Usage: python final.py finalists.json"""
import json, sys
import numpy as np
import harness as H

X, y, season = H.load()
idx = {c: i for i, c in enumerate(H.ALL)}
finalists = json.loads(open(sys.argv[1]).read())
finalists = {"elo": H.ELO, "shipped44": H.SHIPPED, **finalists}


def walk_forward(feats, C=H.C):
    j = [idx[f] for f in feats]
    out = {}
    for t in H.TEST_SEASONS:
        prior = [s for s in H.CV_SEASONS + H.TEST_SEASONS if s < t]
        tr, te = np.isin(season, prior), season == t
        mu, sd = X[tr][:, j].mean(0), X[tr][:, j].std(0); sd[sd == 0] = 1
        b = H.fit((X[tr][:, j] - mu) / sd, y[tr], C)
        out[t] = H.predict(b, (X[te][:, j] - mu) / sd)
    return out


yt = {t: y[season == t] for t in H.TEST_SEASONS}
preds = {}
for name, spec in finalists.items():
    feats, C = (spec["features"], spec.get("C", H.C)) if isinstance(spec, dict) else (spec, H.C)
    preds[name] = walk_forward(feats, C)

rng = np.random.default_rng(0)
yall = np.concatenate([yt[t] for t in H.TEST_SEASONS])
B = rng.integers(0, len(yall), (10000, len(yall)))
ll = {n: np.concatenate([H.logloss(p[t], yt[t]) for t in H.TEST_SEASONS]) for n, p in preds.items()}
print(f"locked test, both teams >= {H.MIN_GP} GP, n={len(yall)}")
print(f"{'set':<22}{'k':>3} {'LL 24-25':>9}{'LL 25-26':>9}{'LL pooled':>10}{'Brier':>8}{'Acc':>7}"
      f"{'P(beats Elo)':>14}{'P(beats 44)':>13}")
res = {}
for n, p in preds.items():
    pa = np.concatenate([p[t] for t in H.TEST_SEASONS])
    spec = finalists[n]
    k = len(spec["features"] if isinstance(spec, dict) else spec)
    pe = (ll["elo"][B] - ll[n][B]).mean(1)
    ps = (ll["shipped44"][B] - ll[n][B]).mean(1)
    r = {"k": k, **{t: float(H.logloss(p[t], yt[t]).mean()) for t in H.TEST_SEASONS},
         "pooled": float(ll[n].mean()), "brier": float(np.mean((pa - yall) ** 2)),
         "acc": float(np.mean((pa > .5) == yall)), "wins": int(np.sum((pa > .5) == yall)),
         "p_beats_elo": float((pe > 0).mean()), "p_beats_44": float((ps > 0).mean())}
    res[n] = r
    print(f"{n:<22}{k:>3} {r['20242025']:>9.4f}{r['20252026']:>9.4f}{r['pooled']:>10.4f}"
          f"{r['brier']:>8.4f}{r['acc']:>7.3f}{r['p_beats_elo']:>14.2f}{r['p_beats_44']:>13.2f}")
json.dump(res, open(H.HERE / "results" / "final.json", "w"), indent=1)
