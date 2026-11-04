"""Early season (either team under 5 GP): does last season's xG help Elo?
Prior-season xG = each team's xG rates as of its last game of the previous
season. LOSO over 2015-16..2023-24 (normal seasons scored), then the locked
walk-forward test on 2024-25 / 2025-26."""
import csv, os
import numpy as np
import harness as H

rows = list(csv.DictReader(open(H.HERE / "data" / "rows_nogoalie.csv")))
last = {}  # (season, team) -> (xgf, xga, hd) as of its latest game
for r in sorted(rows, key=lambda r: r["date"]):
    for side in ("home", "away"):
        last[(r["season"], r[f"{side}_team"])] = (
            float(r[f"{side}_xgf_per60"]), float(r[f"{side}_xga_per60"]),
            float(r[f"{side}_high_danger_xg_share"]))
prev = lambda s: f"{int(s[:4]) - 1}{int(s[:4])}"

E = []
for r in rows:
    gp = min(float(r["home_gp"]), float(r["away_gp"]))
    if gp >= H.MIN_GP or r["season"] not in H.CV_SEASONS + H.TEST_SEASONS:
        continue
    ph, pa = last.get((prev(r["season"]), r["home_team"])), last.get((prev(r["season"]), r["away_team"]))
    if ph is None or pa is None:   # expansion team's first season
        ph = ph or (np.nan,) * 3; pa = pa or (np.nan,) * 3
    w = gp / H.MIN_GP              # weight shifts to this season as games accrue
    cur = (float(r["home_xgf_per60"]) - float(r["home_xga_per60"])) - (float(r["away_xgf_per60"]) - float(r["away_xga_per60"]))
    p_xg = (ph[0] - ph[1]) - (pa[0] - pa[1])
    E.append({"season": r["season"], "y": int(r["home_win"]),
              "elo_diff": float(r["elo_diff"]), "rest_diff": float(r["rest_diff"]),
              "home_b2b": float(r["home_b2b"]), "away_b2b": float(r["away_b2b"]),
              "prev_xg_diff": p_xg, "prev_hd_diff": ph[2] - pa[2],
              "blend_xg_diff": (1 - w) * p_xg + w * cur if gp > 0 else p_xg})
for e in E:  # expansion teams: no prior season -> neutral
    for k in ("prev_xg_diff", "prev_hd_diff", "blend_xg_diff"):
        if np.isnan(e[k]):
            e[k] = 0.0

S = np.array([e["season"] for e in E]); y = np.array([e["y"] for e in E])
sets = {"elo": H.ELO, "elo+prev_xg": H.ELO + ["prev_xg_diff"],
        "elo+prev_xg+hd": H.ELO + ["prev_xg_diff", "prev_hd_diff"],
        "elo+blend_xg": H.ELO + ["blend_xg_diff"]}

def run(feats, train_mask, test_mask):
    X = np.array([[e[f] for f in feats] for e in E])
    mu, sd = X[train_mask].mean(0), X[train_mask].std(0)
    b = H.fit((X[train_mask] - mu) / sd, y[train_mask])
    return H.predict(b, (X[test_mask] - mu) / sd)

print(f"early-season rows: {len(E)}")
cv = np.isin(S, H.CV_SEASONS)
for name, f in sets.items():
    ll = np.concatenate([H.logloss(run(f, cv & (S != s), S == s), y[S == s]) for s in H.SCORED])
    test = []
    for t in H.TEST_SEASONS:
        tr = np.isin(S, [s for s in H.CV_SEASONS + H.TEST_SEASONS if s < t])
        test.append(H.logloss(run(f, tr, S == t), y[S == t]))
    test = np.concatenate(test)
    print(f"{name:<18} CV LL {ll.mean():.4f} (n={len(ll)})   locked test LL {test.mean():.4f} (n={len(test)})")
    globals().setdefault("TEST", {})[name] = test
d = TEST["elo"] - TEST["elo+prev_xg"]
B = np.random.default_rng(0).integers(0, len(d), (10000, len(d)))
print(f"elo+prev_xg vs elo on locked test: gain {d.mean():+.4f}, P(gain>0) {(d[B].mean(1) > 0).mean():.2f}")
