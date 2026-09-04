#!/usr/bin/env python3
"""How good is the logistic xG model when its input is a tagged zone?

    train 2018-2023   test 2024 + 2025 (both held-out seasons)

Three ways to feed a zone map to the model, all on the same split:

  A  train on exact coordinates, score zone medians   (what a coordinate model
     does when you hand it eyeballed input -- a mismatch)
  B  retrain on zone medians, score zone medians      (matched)
  C  drop distance/angle entirely and give the model the zone as a category
     (the natural zone model: it learns each zone's own rate)

Zone medians come from the TRAINING seasons only. Run:

    ./.venv/bin/python zone_backtest.py            # 5 features
    ./.venv/bin/python zone_backtest.py --vod      # no shot type, no rebound
"""
import argparse, sys
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.metrics import log_loss, roc_auc_score

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from src.data.schema import assert_no_holdout_leak
import zone_tagging as Z

TRAIN_SEASONS = range(2018, 2024)
TEST_SEASONS = [2024, 2025]


def fit(tr, num, cat, y):
    p = Pipeline([("prep", ColumnTransformer(
        [("num", StandardScaler(), num),
         ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=30), cat)])),
        ("clf", LogisticRegression(max_iter=2000))])
    return p.fit(tr[num + cat], y)


def headline(name, y, p):
    print(f"  {name:<46}AUC {roc_auc_score(y,p):.4f}   ll {log_loss(y,p,labels=[0,1]):.5f}"
          f"   xG/goals {p.sum()/y.sum():.4f}")


def deciles(y, p):
    print(f"\n    {'bucket':<16}{'n':>9}{'mean xG':>10}{'actual':>10}{'ratio':>8}")
    t = pd.DataFrame({"y": np.asarray(y), "p": p, "q": pd.qcut(p, 10, duplicates="drop")})
    for iv, g in t.groupby("q", observed=True):
        act = g.y.mean()
        print(f"    {f'{iv.left:.3f}-{iv.right:.3f}':<16}{len(g):>9,}{g.p.mean():>10.4f}"
              f"{act:>10.4f}{(g.p.mean()/act if act else np.nan):>8.3f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vod", action="store_true",
                    help="drop shot_type and is_rebound (what a VOD tagger really has)")
    ap.add_argument("--drift", action="store_true",
                    help="why the model over-predicts: feature ladder, era drift, train window")
    args = ap.parse_args()

    df = pd.read_parquet(ROOT / "data" / "shots.parquet")
    tr = df[df.season.isin(TRAIN_SEASONS)].copy()
    te = df[df.season.isin(TEST_SEASONS)].copy()
    assert_no_holdout_leak(tr)

    NUM = ["distance", "angle_from_net"] + ([] if args.vod else ["is_rebound"])
    CAT = ["situation"] + ([] if args.vod else ["shot_type"])
    print(f"train {len(tr):,} shots {min(TRAIN_SEASONS)}-{max(TRAIN_SEASONS)}   "
          f"test {len(te):,} shots {TEST_SEASONS}   "
          f"goal rate {tr.goal.mean():.4f} -> {te.goal.mean():.4f}")
    print(f"features: {', '.join(NUM + CAT)}"
          f"{'   [VOD mode: no shot type, no rebound]' if args.vod else ''}\n")

    for part in (tr, te):
        x, y = part.x_adj.to_numpy(float), part.y_adj.to_numpy(float)
        part["zone16"] = Z.zone16(x, y)
        part["zone10"] = Z.zone10(x, y)
        d, a = Z.geometry(np.round(x/5)*5, np.round(y/5)*5)
        part["grid_d"], part["grid_a"] = d, a

    # zone -> median (distance, angle), learned on the training seasons only
    med = {c: tr.groupby(c)[["distance", "angle_from_net"]].median() for c in ("zone16", "zone10")}

    def collapsed(part, col):
        m = med[col]
        out = part.copy()
        out["distance"] = part[col].map(m.distance).to_numpy()
        out["angle_from_net"] = part[col].map(m.angle_from_net).to_numpy()
        return out

    def gridded(part):
        out = part.copy()
        out["distance"], out["angle_from_net"] = part.grid_d, part.grid_a
        return out

    inputs = {"exact coords": (tr, te),
              "16 EDGE zones": (collapsed(tr, "zone16"), collapsed(te, "zone16")),
              "10 hand-cut zones": (collapsed(tr, "zone10"), collapsed(te, "zone10")),
              "5 ft grid": (gridded(tr), gridded(te))}

    m_exact = fit(tr, NUM, CAT, tr.goal)
    print("A. model trained on exact coordinates, scored on tagged input")
    for name, (_, te_i) in inputs.items():
        headline(name, te.goal, m_exact.predict_proba(te_i[NUM + CAT])[:, 1])

    print("\nB. model retrained on the same tagged input")
    fitted = {}
    for name, (tr_i, te_i) in inputs.items():
        m = fit(tr_i, NUM, CAT, tr_i.goal)
        fitted[name] = (m, te_i)
        headline(name, te.goal, m.predict_proba(te_i[NUM + CAT])[:, 1])

    print("\nC. zone as a category, no distance or angle at all")
    zone_models = {}
    for col, label in (("zone16", "16 EDGE zones"), ("zone10", "10 hand-cut zones")):
        num_c = [c for c in NUM if c not in ("distance", "angle_from_net")]
        m = fit(tr, num_c, [col] + CAT, tr.goal)
        p = m.predict_proba(te[num_c + [col] + CAT])[:, 1]
        zone_models[label] = (m, num_c + [col] + CAT, p)
        headline(label, te.goal, p)
    headline("moneypuck (reference, uses exact coords)", te.goal,
             te.mp_xg.clip(1e-6, 1 - 1e-6).to_numpy())

    best_p = zone_models["16 EDGE zones"][2]
    exact_p = m_exact.predict_proba(te[NUM + CAT])[:, 1]

    print("\n--- the 16-zone categorical model, held out ---")
    print("\n  per season")
    for s in TEST_SEASONS:
        m = (te.season == s).to_numpy()
        headline(f"{s}  (n={m.sum():,})", te.goal[m], best_p[m])
    print("\n  calibration by predicted decile")
    deciles(te.goal, best_p)

    print("\n  per zone: does it get each zone's rate right?")
    t = te.assign(p=best_p, pe=exact_p)
    g = t.groupby("zone16").agg(n=("p", "size"), goals=("goal", "sum"),
                                actual=("goal", "mean"), xg=("p", "mean"),
                                xg_exact=("pe", "mean"))
    g["ratio"] = g.xg / g.actual
    g["exact_ratio"] = g.xg_exact / g.actual
    print(f"    {'zone':<18}{'n':>8}{'goals':>7}{'actual':>9}{'xG':>9}{'ratio':>8}{'exact ratio':>13}")
    for z, r in g.iterrows():
        print(f"    {z:<18}{int(r.n):>8,}{int(r.goals):>7,}{r.actual:>9.4f}{r.xg:>9.4f}"
              f"{r.ratio:>8.3f}{r.exact_ratio:>13.3f}")
    print(f"    {'mean |ratio-1|':<18}{'':>24}{'':>9}{np.abs(g.ratio-1).mean():>8.3f}"
          f"{np.abs(g.exact_ratio-1).mean():>13.3f}")

    if args.drift:
        drift_report(df.assign(zone16=Z.zone16(df.x_adj.to_numpy(float), df.y_adj.to_numpy(float))),
                     tr, te)

    print("\n  calibration by situation")
    print(f"    {'situation':<22}{'n':>9}{'goals':>8}{'xG':>10}{'ratio':>8}")
    errs = []
    for sit, gg in t.groupby("situation"):
        if len(gg) < 300 or gg.goal.sum() == 0:
            continue
        ratio = gg.p.sum() / gg.goal.sum(); errs.append(abs(ratio - 1))
        print(f"    {sit:<22}{len(gg):>9,}{int(gg.goal.sum()):>8,}{gg.p.sum():>10.1f}{ratio:>8.3f}")
    print(f"    {'mean abs error':<22}{'':>27}{np.mean(errs):>8.4f}")


def drift_report(df, tr, te):
    """The held-out seasons are not drawn from the training distribution. This
    is where the over-prediction comes from -- and where it does not."""
    print("\n=== 1. is it the zone mix? apply train zone rates to the test mix ===")
    rate = tr.groupby("zone16").goal.mean(); n = te.groupby("zone16").goal.size()
    print(f"  actual goals 2024-25              {te.goal.sum():>8,.0f}")
    print(f"  train zone rates x test zone mix  {(n*rate).sum():>8,.0f}"
          f"   ratio {(n*rate).sum()/te.goal.sum():.4f}   <- the map itself is unbiased")

    print("\n=== 2. so which feature does it? build the model up one at a time ===")
    def run(num, cat, label):
        m = fit(tr, num, cat, tr.goal)
        p = m.predict_proba(te[num + cat])[:, 1]
        headline(label, te.goal, p)
    run([], ["zone16"], "zone only")
    run([], ["zone16", "situation"], "zone + situation")
    run(["is_rebound"], ["zone16", "situation"], "zone + situation + rebound")
    run(["is_rebound"], ["zone16", "situation", "shot_type"], "zone + situation + rebound + shot type")

    print("\n=== 3. shot type is relabelled between the eras ===")
    a = tr.groupby("shot_type").goal.agg(train_share=lambda s: len(s)/len(tr)*100, train_rate="mean")
    b = te.groupby("shot_type").goal.agg(test_share=lambda s: len(s)/len(te)*100, test_rate="mean")
    t = a.join(b); t["rate_shift"] = t.test_rate / t.train_rate
    print(t.round(3).to_string())

    print("\n=== 4. the zone mix moves too (share of shots, %) ===")
    print((pd.crosstab(df.zone16, df.season, normalize="columns")*100).round(2).to_string())

    print("\n=== 5. does a shorter training window help? ===")
    for label, yrs in [("2018-2023 (the ask)", range(2018,2024)), ("2021-2023", range(2021,2024)),
                       ("2022-2023", range(2022,2024)), ("2023 only", [2023])]:
        t2 = df[df.season.isin(yrs)]
        m = fit(t2, ["is_rebound"], ["zone16", "situation", "shot_type"], t2.goal)
        p = m.predict_proba(te[["is_rebound", "zone16", "situation", "shot_type"]])[:, 1]
        headline(f"16-zone model, train {label}", te.goal, p)


if __name__ == "__main__":
    main()
