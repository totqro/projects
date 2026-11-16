"""
Fit the season-projection model and back-test it (projections.py).

Reads every regular-season result since 2014-15 from cached NHL club
schedules (nhllines/cache/club_season_<TEAM>_<season>.json) and High Slot's
walk-forward 5v5 xG per team-game since 2017-18
(nhllines/data/highslot_team_game_xg.json, written by export_team_game_xg.py).
Each season's xG there comes from a model trained only on earlier seasons,
so the back-test never sees xG fitted on the games it predicts.

Writes:
  data/projection_model.json   coefficients, overtime rates, goal margins,
                               sigma and the Elo seed nhl_projections.py
                               starts from
  ../app/playoffs/backtest.json  the back-test the Playoff odds page shows

Back-test: 2017-18, 2018-19 and 2021-22 to 2025-26 (2019-20 and 2020-21 had
other playoff formats), from Nov 15, Dec 15, Jan 15, Feb 15 and Mar 15 of
each. Every season is projected by a model fit on the other seasons, and
sigma is picked on the other seasons too. "Made the playoffs" is read from
the schedules (the teams that played a playoff game).

Refit each summer, after the season's schedules and xG are cached:

    .venv/bin/python fit_projections.py \
        --schedules ../../nhllines/cache --xg ../../nhllines/data/highslot_team_game_xg.json
"""

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

import projections as P

HERE = Path(__file__).resolve().parent
MODEL_OUT = HERE / "data" / "projection_model.json"
BACKTEST_OUT = HERE.parent / "app" / "playoffs" / "backtest.json"

FIRST_SEASON = 2014          # Elo warm-up
XG_FIRST = 2017              # High Slot walk-forward xG starts here
LAST_SEASON = 2025           # last completed season
BACKTEST = [2017, 2018, 2021, 2022, 2023, 2024, 2025]
CHECKPOINTS = [("11-15", "Nov 15"), ("12-15", "Dec 15"), ("01-15", "Jan 15"), ("02-15", "Feb 15"), ("03-15", "Mar 15")]
SIGMAS = [0.0, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4]
CORE = ["elo_diff", "xgd_diff", "home_b2b", "away_b2b"]
EARLY = ["elo_diff", "home_b2b", "away_b2b"]


# ------------------------------------------------------------------- data

def load_games(sched_dir: Path, xg_file: Path):
    """All final regular-season games, sorted, plus each season's playoff teams."""
    xg = json.loads(xg_file.read_text())["games"]
    games, playoff_teams = {}, defaultdict(set)
    for f in sorted(sched_dir.glob("club_season_*_*.json")):
        season = int(f.stem.split("_")[-1][:4])
        if not FIRST_SEASON <= season <= LAST_SEASON:
            continue
        for g in json.loads(f.read_text()):
            if g.get("gameState") not in ("OFF", "FINAL"):
                continue
            if g["gameType"] == 3:
                playoff_teams[season].update((g["homeTeam"]["abbrev"], g["awayTeam"]["abbrev"]))
            if g["gameType"] != 2 or g["id"] in games:
                continue
            h, a = g["homeTeam"], g["awayTeam"]
            row = {"id": g["id"], "season": season, "date": g["gameDate"], "home": h["abbrev"], "away": a["abbrev"],
                   "hs": h["score"], "as": a["score"], "end": g["gameOutcome"]["lastPeriodType"]}
            x = xg.get(str(g["id"]))
            if x and row["home"] in x and row["away"] in x:
                row["hx5"], row["ax5"] = x[row["home"]]["xgf5"], x[row["away"]]["xgf5"]
            games[g["id"]] = row
    return sorted(games.values(), key=lambda g: (g["date"], g["id"])), playoff_teams


def season_dates(games):
    out = defaultdict(lambda: defaultdict(set))
    for g in games:
        out[g["season"]][g["home"]].add(g["date"])
        out[g["season"]][g["away"]].add(g["date"])
    return out


def build_rows(games, dates):
    """Point-in-time features for every game, in order."""
    elo = P.Elo()
    tallies, cur = {}, None
    rows = []
    for g in games:
        s = g["season"]
        if s != cur:
            tallies, cur = {}, s
        th, ta = tallies.get(g["home"], P.Tally()), tallies.get(g["away"], P.Tally())
        rows.append({
            "id": g["id"], "season": s, "y": int(g["hs"] > g["as"]), "end": g["end"],
            "margin": abs(g["hs"] - g["as"]),
            "elo_diff": elo.rating(g["home"], s) - elo.rating(g["away"], s),
            "xgd_diff": th.xgd - ta.xgd,
            "home_b2b": P.b2b_flags(dates[s], g["home"], g["date"]),
            "away_b2b": P.b2b_flags(dates[s], g["away"], g["date"]),
            "min_gp": min(th.gp, ta.gp), "min_xg_gp": min(th.xg_gp, ta.xg_gp),
        })
        elo.update(g["home"], g["away"], g["hs"] > g["as"], s)
        P.record_game(tallies, g)
    return rows


def is_core(r):
    return r["season"] >= XG_FIRST and r["min_xg_gp"] >= P.MIN_GP


def is_early(r):
    return r["season"] >= 2015 and r["min_gp"] < P.MIN_GP


def fit_logistic(rows, cols):
    """L2 logistic, C=0.1 on standardised features (core4's settings),
    returned in raw feature units."""
    X = np.array([[r[c] for c in cols] for r in rows])
    y = np.array([r["y"] for r in rows])
    sc = StandardScaler().fit(X)
    m = LogisticRegression(C=0.1, max_iter=2000).fit(sc.transform(X), y)
    coef = m.coef_[0] / sc.scale_
    out = dict(zip(cols, coef.tolist()))
    out["intercept"] = float(m.intercept_[0] - np.sum(m.coef_[0] * sc.mean_ / sc.scale_))
    return out


def fit_model(rows, exclude=()):
    core = fit_logistic([r for r in rows if is_core(r) and r["season"] not in exclude], CORE)
    early = fit_logistic([r for r in rows if is_early(r) and r["season"] not in exclude], EARLY)
    return {"core": core, "early": early}


def model_p(model, r):
    early = r["min_xg_gp"] < P.MIN_GP or r["season"] < XG_FIRST
    return float(P.sigmoid(P.game_logit(model, r["elo_diff"], r["xgd_diff"], r["home_b2b"], r["away_b2b"], early)))


def overtime(rows, model):
    """Overtime rate, shootout share and how much of a favourite's edge
    survives extra time, from the 3-on-3 era (2015-16 on)."""
    rs = [r for r in rows if r["season"] >= 2015]
    extra = [r for r in rs if r["end"] != "REG"]
    p = np.array([model_p(model, r) for r in extra]) - 0.5
    y = np.array([r["y"] for r in extra]) - 0.5
    margins = np.bincount([min(r["margin"], 8) for r in rs if r["end"] == "REG"], minlength=9)[1:]
    return ({"rate": len(extra) / len(rs), "so_share": sum(r["end"] == "SO" for r in extra) / len(extra),
             "k": float(np.sum(p * y) / np.sum(p * p))},
            (margins / margins.sum()).round(5).tolist())


def log_loss(p, y):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    y = np.asarray(y, float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


# -------------------------------------------------------------- back-test

def checkpoint_state(games, season, date):
    """Elo, this season's tallies and remaining games as of `date`."""
    elo = P.Elo()
    tallies = {}
    remaining = []
    for g in games:
        if g["season"] > season:
            break
        if g["season"] == season and g["date"] >= date:
            remaining.append(g)
            continue
        elo.update(g["home"], g["away"], g["hs"] > g["as"], g["season"])
        if g["season"] == season:
            P.record_game(tallies, g)
    return elo.snapshot(season), tallies, remaining


def backtest(games, rows, playoff_teams, dates, base, n):
    """Per (season, checkpoint, sigma): every team's playoff %, projected
    points, 80% range, and what happened."""
    out = []
    for s in BACKTEST:
        model = {**fit_model(rows, exclude={s}), **base}
        align = P.alignment(s)
        final = {}
        for g in games:
            if g["season"] == s:
                P.record_game(final, g)
        _, fres = P.simulate(model, align, final, [], {}, n=1, sigma=0)
        teams = sorted(align)
        for md, label in CHECKPOINTS:
            date = f"{s + (md < '09')}-{md}"
            elo, tallies, remaining = checkpoint_state(games, s, date)
            for sigma in SIGMAS:
                tm, res = P.simulate(model, align, tallies, remaining, elo, n=n, sigma=sigma,
                                     seed=s, dates_by_team=dates[s])
                for i, t in enumerate(tm):
                    col = res["pts"][:, i]
                    out.append({
                        "season": s, "cp": label, "sigma": sigma, "team": t,
                        "p": float(res["playoff"][:, i].mean()), "pdiv": float(res["divwin"][:, i].mean()),
                        "proj": float(col.mean()), "lo": float(np.percentile(col, 10)), "hi": float(np.percentile(col, 90)),
                        "made": int(t in playoff_teams[s]), "won_div": int(fres["divwin"][0, teams.index(t)]),
                        "final": final[t].pts,
                    })
            # Coin-flip baseline: every remaining game at the league's home win rate.
            flip = {"core": {k: 0.0 for k in ["intercept", *CORE]}, "early": {k: 0.0 for k in ["intercept", *EARLY]}, **base}
            flip["core"]["intercept"] = flip["early"]["intercept"] = base["home_logit"]
            tm, res = P.simulate(flip, align, tallies, remaining, elo, n=n, sigma=0, seed=s, dates_by_team=dates[s])
            for i, t in enumerate(tm):
                out.append({"season": s, "cp": label, "sigma": "flip", "team": t, "p": float(res["playoff"][:, i].mean()),
                            "proj": float(res["pts"][:, i].mean()), "made": int(t in playoff_teams[s]), "final": final[t].pts})
        print(f"  back-test {s}-{(s + 1) % 100:02d} done", flush=True)
    return out


def score(rs):
    p = np.array([r["p"] for r in rs])
    y = np.array([r["made"] for r in rs])
    err = np.array([r["proj"] - r["final"] for r in rs])
    d = {"n": len(rs), "brier": round(float(np.mean((p - y) ** 2)), 4), "log_loss": round(log_loss(p, y), 4),
         "pts_mae": round(float(np.mean(np.abs(err))), 2)}
    if "lo" in rs[0]:
        d["pts_cover80"] = round(float(np.mean([r["lo"] <= r["final"] <= r["hi"] for r in rs])), 3)
    return d


def summarize_backtest(bt):
    """Pick sigma per season on the other seasons, then score."""
    chosen = {}
    for s in BACKTEST:
        others = {sg: log_loss([r["p"] for r in bt if r["sigma"] == sg and r["season"] != s],
                               [r["made"] for r in bt if r["sigma"] == sg and r["season"] != s]) for sg in SIGMAS}
        chosen[s] = min(others, key=others.get)
    picked = [r for r in bt if r["sigma"] == chosen[r["season"]]]
    flip = [r for r in bt if r["sigma"] == "flip"]
    bins = []
    edges = [0, 0.05, 0.2, 0.35, 0.5, 0.65, 0.8, 0.95, 1.0001]
    for lo, hi in zip(edges, edges[1:]):
        b = [r for r in picked if lo <= r["p"] < hi]
        if b:
            bins.append({"lo": lo, "hi": min(hi, 1), "n": len(b), "pred": round(float(np.mean([r["p"] for r in b])), 3),
                         "obs": round(float(np.mean([r["made"] for r in b])), 3)})
    by_cp = []
    for _, label in CHECKPOINTS:
        m = score([r for r in picked if r["cp"] == label])
        f = score([r for r in flip if r["cp"] == label])
        by_cp.append({"cp": label, **m, "flip_brier": f["brier"], "flip_pts_mae": f["pts_mae"]})
    by_sigma = {str(sg): score([r for r in bt if r["sigma"] == sg]) for sg in SIGMAS}
    all_ll = {sg: by_sigma[str(sg)]["log_loss"] for sg in SIGMAS}
    return {
        "seasons": BACKTEST, "checkpoints": [c[1] for c in CHECKPOINTS],
        "sigma_by_season": {str(k): v for k, v in chosen.items()},
        "sigma": min(all_ll, key=all_ll.get),
        "overall": score(picked), "flip": score(flip), "bins": bins, "by_checkpoint": by_cp, "by_sigma": by_sigma,
    }


def compare_core4(rows, rows_csv: Path):
    """Walk-forward per-game log loss on 2024-25 and 2025-26: core4 on
    MoneyPuck xG (feature_search's rows, as final.py fit it) next to the
    refit on High Slot xG, on the games both cover."""
    import csv
    mp = {}
    with open(rows_csv) as f:
        for d in csv.DictReader(f):
            if min(float(d["home_gp"]), float(d["away_gp"])) >= P.MIN_GP:
                mp[int(d["game_id"])] = {"season": int(d["season"][:4]), "y": int(d["home_win"]),
                                         "elo_diff": float(d["elo_diff"]), "xg_diff_rate_diff": float(d["xg_diff_rate_diff"]),
                                         "home_b2b": float(d["home_b2b"]), "away_b2b": float(d["away_b2b"])}
    out = {}
    for s in (2024, 2025):
        hs_fit = fit_logistic([r for r in rows if is_core(r) and r["season"] < s], CORE)
        mp_fit = fit_logistic([r for r in mp.values() if 2015 <= r["season"] < s],
                              ["elo_diff", "xg_diff_rate_diff", "home_b2b", "away_b2b"])
        test = [r for r in rows if r["season"] == s and is_core(r) and r["id"] in mp]
        y = [r["y"] for r in test]
        p_hs = [float(P.sigmoid(hs_fit["intercept"] + sum(hs_fit[c] * r[c] for c in CORE))) for r in test]
        p_mp = [float(P.sigmoid(mp_fit["intercept"] + sum(mp_fit[c] * mp[r["id"]][c] for c in mp_fit if c != "intercept")))
                for r in test]
        out[str(s)] = {"n": len(test), "core4_highslot": round(log_loss(p_hs, y), 4), "core4_moneypuck": round(log_loss(p_mp, y), 4)}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--schedules", type=Path, required=True)
    ap.add_argument("--xg", type=Path, required=True)
    ap.add_argument("--core4-rows", type=Path, help="feature_search/data/rows_nogoalie.csv, to compare with MoneyPuck core4")
    ap.add_argument("--sims", type=int, default=3000, help="seasons per back-test projection")
    a = ap.parse_args()

    games, playoff_teams = load_games(a.schedules, a.xg)
    dates = season_dates(games)
    rows = build_rows(games, dates)
    print(f"{len(games)} games, {sum(map(is_core, rows))} core rows, {sum(map(is_early, rows))} early rows")

    model = fit_model(rows)
    ot, margins = overtime(rows, model)
    home_rate = float(np.mean([r["y"] for r in rows if r["season"] >= 2015]))
    base = {"ot": ot, "margins": margins, "home_logit": float(np.log(home_rate / (1 - home_rate)))}
    print("model", json.dumps(model), "\novertime", ot)

    bt = backtest(games, rows, playoff_teams, dates, base, a.sims)
    summary = summarize_backtest(bt)
    if a.core4_rows:
        summary["core4_compare"] = compare_core4(rows, a.core4_rows)
    summary["model_games"] = {"core": sum(map(is_core, rows)), "early": sum(map(is_early, rows))}
    summary["fitted"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(json.dumps({k: summary[k] for k in ("sigma", "sigma_by_season", "overall", "flip", "by_checkpoint")}, indent=1))

    # Elo seed: ratings after LAST_SEASON - 1. The nightly run replays the
    # published seasons after it from the site's own game index.
    elo = P.Elo()
    for g in games:
        if g["season"] < LAST_SEASON:
            elo.update(g["home"], g["away"], g["hs"] > g["as"], g["season"])
    seed = {"season": LAST_SEASON - 1, "ratings": {t: round(r, 2) for t, r in sorted(elo.ratings.items())
                                                    if elo.season[t] == LAST_SEASON - 1}}

    MODEL_OUT.write_text(json.dumps({
        "version": f"core4-hs-{summary['fitted']}",
        "note": "core4 (Elo, 5v5 xG differential per game, back-to-backs) refit on High Slot xG. fit_projections.py.",
        "trained_on": {"core": f"{XG_FIRST}-{LAST_SEASON}", "early": f"2015-{LAST_SEASON}"},
        "min_gp": P.MIN_GP, **model, "ot": ot, "margins": margins, "sigma": summary["sigma"],
        "elo": {"k": P.ELO_K, "reversion": P.ELO_REVERSION}, "elo_seed": seed,
    }, indent=1) + "\n")
    BACKTEST_OUT.parent.mkdir(parents=True, exist_ok=True)
    BACKTEST_OUT.write_text(json.dumps({k: v for k, v in summary.items() if k != "by_sigma"} | {"by_sigma": summary["by_sigma"]}, indent=1) + "\n")
    print(f"wrote {MODEL_OUT.relative_to(HERE.parent)} and {BACKTEST_OUT.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
