"""Feature-subset searches, all scored by harness.Evaluator (LOSO 2015-24).
Usage: python search.py <method> ; results go to results/<method>.json"""
import os
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
import itertools, json, multiprocessing as mp, random, sys, time
import numpy as np
import harness as H

OUT = H.HERE / ("results_nogoalie" if H.NO_GOALIE else "results")
OUT.mkdir(exist_ok=True)
EV = None


def _init():
    global EV
    if EV is None:
        EV = H.Evaluator()


def _score(feats):
    return EV.score(list(feats))


def pool():
    return mp.get_context("fork").Pool(10, initializer=_init)


def save(name, obj):
    (OUT / f"{name}.json").write_text(json.dumps(obj, indent=1))
    print(f"saved results/{name}.json", flush=True)


def baselines():
    out = {}
    for name, f in [("elo", H.ELO), ("shipped44", H.SHIPPED), *([] if H.NO_GOALIE else [("shipped+goalie", H.SHIPPED + H.GOALIE)]),
                    ("all", H.ALL), ("elo_only_diff", ["elo_diff"])]:
        out[name] = EV.score(f, detail=True) | {"features": f}
        print(f"{name:<18} {out[name]['logloss']:.5f} acc {out[name]['acc']:.4f}", flush=True)
    save("baselines", out)


def forward(start=(), name="forward"):
    chosen, path = list(start), []
    with pool() as P:
        while len(chosen) < len(H.ALL):
            cand = [c for c in H.ALL if c not in chosen]
            scores = P.map(_score, [chosen + [c] for c in cand])
            best = int(np.argmin(scores))
            chosen.append(cand[best])
            path.append({"k": len(chosen), "added": cand[best], "logloss": scores[best]})
            print(f"{len(chosen):>2} +{cand[best]:<28} {scores[best]:.5f}", flush=True)
    save(name, {"start": list(start), "path": path})


def backward():
    chosen, path = list(H.ALL), [{"k": len(H.ALL), "removed": None, "logloss": EV.score(H.ALL)}]
    with pool() as P:
        while len(chosen) > 1:
            scores = P.map(_score, [[c for c in chosen if c != r] for r in chosen])
            best = int(np.argmin(scores))
            r = chosen.pop(best)
            path.append({"k": len(chosen), "removed": r, "logloss": scores[best], "features": list(chosen)})
            print(f"{len(chosen):>2} -{r:<28} {scores[best]:.5f}", flush=True)
    save("backward", {"path": path})


def floating():
    """Sequential floating forward selection: add the best, then drop any
    feature whose removal beats the best set seen at that size."""
    chosen, best_at = [], {}
    with pool() as P:
        while len(chosen) < 35:
            cand = [c for c in H.ALL if c not in chosen]
            s = P.map(_score, [chosen + [c] for c in cand])
            chosen = chosen + [cand[int(np.argmin(s))]]
            cur = min(s)
            if cur < best_at.get(len(chosen), (9, None))[0]:
                best_at[len(chosen)] = (cur, list(chosen))
            while len(chosen) > 2:
                s = P.map(_score, [[c for c in chosen if c != r] for r in chosen])
                j = int(np.argmin(s))
                k = len(chosen) - 1
                if s[j] < best_at.get(k, (9, None))[0] - 1e-7:
                    chosen = [c for i, c in enumerate(chosen) if i != j]
                    best_at[k] = (s[j], list(chosen))
                    print(f"   drop -> k={k} {s[j]:.5f}", flush=True)
                else:
                    break
            print(f"k={len(chosen)} {cur:.5f} {chosen[-1]}", flush=True)
    save("floating", {str(k): {"logloss": v[0], "features": v[1]} for k, v in sorted(best_at.items())})


BLOCKS = {
    "elo": ["elo_diff"],
    "record": ["home_win_pct", "home_points_pct", "away_win_pct", "away_points_pct", "win_pct_diff", "points_pct_diff"],
    "venue_record": ["home_home_win_pct", "away_road_win_pct", "venue_win_pct_diff"],
    "goals_pg": ["home_gf_pg", "home_ga_pg", "away_gf_pg", "away_ga_pg", "goal_diff_rate_diff"],
    "form": ["home_form_win_pct", "away_form_win_pct", "form_diff"],
    "form_goals": ["home_form_gf", "home_form_ga", "away_form_gf", "away_form_ga", "form_goal_diff"],
    "streak_trend": ["home_streak", "home_trend", "away_streak", "away_trend", "streak_diff"],
    "rest": ["home_rest_days", "away_rest_days", "home_b2b", "away_b2b", "rest_diff"],
    "gp": ["home_gp", "away_gp"],
    "xg_rates": ["home_xgf_per60", "home_xga_per60", "away_xgf_per60", "away_xga_per60",
                 "xg_diff_rate_diff", "xgf_diff", "xga_diff"],
    "high_danger": ["home_high_danger_xg_share", "away_high_danger_xg_share", "hd_share_diff"],
    "xg_luck": ["home_xg_luck_for", "home_xg_luck_against", "away_xg_luck_for",
                "away_xg_luck_against", "xg_luck_net_diff"],
    **({} if H.NO_GOALIE else {"goalie": H.GOALIE + ["goalie_gaa_diff"]}),
    "h2h": ["h2h_home_win_rate", "h2h_meetings"],
}
# Diff-only version of each block: one or two summary numbers per idea.
DIFF_BLOCKS = {
    "elo": ["elo_diff"], "record": ["points_pct_diff"], "venue_record": ["venue_win_pct_diff"],
    "goals_pg": ["goal_diff_rate_diff"], "form": ["form_diff"], "form_goals": ["form_goal_diff"],
    "streak_trend": ["streak_diff"], "rest": ["rest_diff", "home_b2b", "away_b2b"],
    "xg_rates": ["xgf_diff", "xga_diff"], "high_danger": ["hd_share_diff"],
    "xg_luck": ["xg_luck_net_diff"],
    **({} if H.NO_GOALIE else {"goalie": ["goalie_sv_pct_diff", "goalie_gaa_diff"]}),
    "h2h": ["h2h_home_win_rate"],
}


def _blocks(blocks, name):
    names = list(blocks)
    subsets = [s for k in range(1, len(names) + 1) for s in itertools.combinations(names, k)]
    print(f"{len(subsets)} block subsets", flush=True)
    feats = [sorted({f for b in s for f in blocks[b]}) for s in subsets]
    with pool() as P:
        scores = P.map(_score, feats, chunksize=64)
    order = np.argsort(scores)
    res = [{"blocks": list(subsets[i]), "logloss": scores[i], "k": len(feats[i])} for i in order]
    for r in res[:15]:
        print(f"{r['logloss']:.5f} k={r['k']:>2} {'+'.join(r['blocks'])}", flush=True)
    save(name, {"top": res[:500], "n": len(res)})


def blocks():
    _blocks(BLOCKS, "blocks")


def diffblocks():
    _blocks(DIFF_BLOCKS, "diffblocks")


def exhaustive(kmax=int(os.environ.get("KMAX", 5))):
    best = {}
    with pool() as P:
        for k in range(1, kmax + 1):
            combos = list(itertools.combinations(H.ALL, k))
            t = time.time()
            scores = P.map(_score, combos, chunksize=256)
            order = np.argsort(scores)[:50]
            best[k] = [{"features": list(combos[i]), "logloss": scores[i]} for i in order]
            print(f"k={k} {len(combos)} subsets in {time.time() - t:.0f}s, best {scores[order[0]]:.5f} "
                  f"{combos[order[0]]}", flush=True)
            save("exhaustive", best)


def anneal(runs=100, steps=3000):
    """Simulated annealing over subsets of any size, random restarts.
    Moves: add, drop or swap one feature."""
    with pool() as P:
        res = P.map(_anneal_one, [(seed, steps) for seed in range(runs)], chunksize=1)
    res.sort(key=lambda r: r["logloss"])
    for r in res[:10]:
        print(f"{r['logloss']:.5f} k={len(r['features'])} seed={r['seed']}", flush=True)
    save("anneal", res)


def _anneal_one(args):
    seed, steps = args
    rng = random.Random(seed)
    k0 = rng.randint(5, 30)
    cur = rng.sample(H.ALL, k0)
    cur_s = EV.score(cur)
    best, best_s = list(cur), cur_s
    T0 = 0.002
    for i in range(steps):
        T = T0 * (1 - i / steps) + 1e-6
        nxt = list(cur)
        move = rng.random()
        out = [c for c in H.ALL if c not in nxt]
        if move < 0.33 and out:
            nxt.append(rng.choice(out))
        elif move < 0.66 and len(nxt) > 1:
            nxt.remove(rng.choice(nxt))
        elif out:
            nxt[rng.randrange(len(nxt))] = rng.choice(out)
        s = EV.score(nxt)
        if s < cur_s or rng.random() < np.exp((cur_s - s) / T):
            cur, cur_s = nxt, s
            if s < best_s:
                best, best_s = list(nxt), s
    return {"seed": seed, "logloss": best_s, "features": sorted(best)}


def genetic(pop_n=300, gens=250, k_target=None):
    rng = np.random.default_rng(1)
    p = len(H.ALL)
    popl = rng.random((pop_n, p)) < rng.uniform(0.1, 0.5, (pop_n, 1))
    def feats(m):
        return [H.ALL[i] for i in np.flatnonzero(m)] or ["elo_diff"]
    with pool() as P:
        for g in range(gens):
            fit = np.array(P.map(_score, [feats(m) for m in popl], chunksize=8))
            order = np.argsort(fit)
            if g % 10 == 0 or g == gens - 1:
                print(f"gen {g} best {fit[order[0]]:.5f} k={popl[order[0]].sum()}", flush=True)
            elite = popl[order[:20]]
            kids = []
            while len(kids) < pop_n - 20:
                a, b = [popl[order[min(rng.integers(0, pop_n, 2))]] for _ in range(2)]
                child = np.where(rng.random(p) < .5, a, b)
                child ^= rng.random(p) < 1.5 / p
                kids.append(child)
            popl = np.vstack([elite, kids])
    fit = np.array([EV.score(feats(m)) for m in popl])
    order = np.argsort(fit)
    save("genetic", [{"logloss": float(fit[i]), "features": feats(popl[i])} for i in order[:30]])


def lasso():
    """L1 path: sklearn liblinear L1 at many C, scored on the same folds."""
    from sklearn.linear_model import LogisticRegression
    out = []
    for Cl in np.logspace(-3.3, 0, 30):
        losses, nz = [], []
        for s, Xtr, ytr, Xte, yte in EV.folds:
            if s not in H.SCORED:
                continue
            m = LogisticRegression(penalty="l1", C=Cl, solver="liblinear", max_iter=5000).fit(Xtr, ytr)
            losses.append(H.logloss(m.predict_proba(Xte)[:, 1], yte))
            nz.append(set(np.array(H.ALL)[m.coef_[0] != 0]))
        allfit = LogisticRegression(penalty="l1", C=Cl, solver="liblinear", max_iter=5000)
        X = EV.X[np.isin(EV.season, H.CV_SEASONS)]
        mu, sd = X.mean(0), X.std(0); sd[sd == 0] = 1
        allfit.fit((X - mu) / sd, EV.y[np.isin(EV.season, H.CV_SEASONS)])
        sel = [f for f, w in zip(H.ALL, allfit.coef_[0]) if w != 0]
        ll = float(np.concatenate(losses).mean())
        out.append({"C": Cl, "logloss": ll, "k": len(sel), "features": sel,
                    "always_selected": sorted(set.intersection(*nz)) if nz else []})
        print(f"C={Cl:.4f} {ll:.5f} k={len(sel)}", flush=True)
    save("lasso", out)


def ctune():
    """Regularisation sweep on the leading candidate sets."""
    import glob
    cands = {"elo": H.ELO, "shipped44": H.SHIPPED, "all": H.ALL}
    for f in ["floating", "anneal", "genetic"]:
        p = OUT / f"{f}.json"
        if p.exists():
            d = json.loads(p.read_text())
            if f == "floating":
                k = min(d, key=lambda k: d[k]["logloss"]); cands[f] = d[k]["features"]
            else:
                cands[f] = d[0]["features"]
    out = {}
    for name, feats in cands.items():
        out[name] = {str(c): EV.score(feats, C=c) for c in [0.001, 0.003, 0.01, 0.03, 0.1, 0.3, 1, 10]}
        b = min(out[name], key=out[name].get)
        print(f"{name:<10} best C={b} {out[name][b]:.5f} (C=0.1: {out[name]['0.1']:.5f})", flush=True)
    save("ctune", out)


if __name__ == "__main__":
    _init()
    method = sys.argv[1]
    t = time.time()
    {"baselines": baselines, "forward": forward, "forward_elo": lambda: forward(H.ELO, "forward_elo"),
     "backward": backward, "floating": floating, "blocks": blocks, "diffblocks": diffblocks,
     "exhaustive": exhaustive, "anneal": anneal, "genetic": genetic, "lasso": lasso,
     "ctune": ctune}[method]()
    print(f"{method} done in {time.time() - t:.0f}s", flush=True)
