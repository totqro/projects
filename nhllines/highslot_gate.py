"""
High Slot xG vs MoneyPuck xG in the win model, and a preseason prior vs the
Elo early-season fallback.
==========================================================================
Two questions, both answered on held-out seasons with log loss and Brier
(the model gate's rules: a candidate must win BOTH to count):

1. Source. Does the shipped 44-feature drop-goalie logistic do better with
   High Slot's xG (src/data/highslot_xg.py) than with MoneyPuck's? Candidates:
     mp      MoneyPuck, 5v5 close + high-danger share (what ships)
     mp-hd   MoneyPuck, high-danger share dropped
     mp5     MoneyPuck, 5v5 any score, high-danger dropped (hs5's definition,
             to tell a better source from a better definition)
     hs      High Slot, 5v5 close + high-danger share (training-only detail)
     hs-hd   High Slot, 5v5 close, high-danger dropped
     hs5     High Slot, 5v5 any score, high-danger dropped. The only High
             Slot variant serving can build, from the site's games.json.
   Scored on the shipped split (train 2022-23..2024-25, test 2025-26) and
   leave-one-season-out over 2018-19..2025-26, with Elo alongside.

2. Early season. main.py serves Elo until both teams have 5 games
   (XG_MIN_GP). On exactly those games, does last season's High Slot 5v5 xG
   share beat Elo? Leave-one-season-out over 2018-19..2025-26, every model
   fitted on early-season games of the other seasons only.

Rows are rebuilt here from cached schedules for every source, so every
candidate sees the same games. Goalie features are left out (the shipped
model drops them), so no boxscores are needed.

Usage:
    python highslot_gate.py                       # prints tables
    python highslot_gate.py --json data/highslot_gate.json
"""

import argparse
import json
import warnings

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss
from sklearn.preprocessing import StandardScaler

import src.data.historical_dataset as hd
from model_gate import ANOMALOUS_LOSO_SEASONS, _attach_elo_from_games
from src.data.highslot_xg import HIGHSLOT_XG_PATH, load_highslot_xg
from src.data.moneypuck_data import load_moneypuck_xg

warnings.filterwarnings("ignore", message=".*matmul.*", category=RuntimeWarning)

SEASONS = [f"{y}{y + 1}" for y in range(2018, 2026)]
SHIPPED_TEST = "20252026"
SHIPPED_TRAIN = ["20222023", "20232024", "20242025"]
EARLY_GP = 5  # main.py XG_MIN_GP

HD_COLUMNS = ["home_high_danger_xg_share", "away_high_danger_xg_share"]
SHIPPED_COLUMNS = hd.XG_FEATURE_COLUMNS
NO_HD_COLUMNS = [c for c in SHIPPED_COLUMNS if c not in HD_COLUMNS]
ELO_COLUMNS = ["elo_diff", "rest_diff", "home_b2b", "away_b2b"]

# Teams whose previous season was played under another code.
PRIOR_ALIASES = {"UTA": "ARI"}


# --------------------------------------------------------------------------- #
# Rows                                                                         #
# --------------------------------------------------------------------------- #
def _games():
    games = []
    for s in SEASONS:
        games.extend(hd.fetch_season_games_full(s, verbose=False))
    return games


def _covered(g, xg_data):
    t = xg_data.get(g["id"]) or {}
    return g["home_team"] in t and g["away_team"] in t


def _common_games(games, sources):
    """Games every source has xG for. A game only one source covers would
    give the sources different team histories, so it is dropped for all of
    them, and the count is reported rather than hidden."""
    keep = [g for g in games if all(_covered(g, x) for x in sources.values())]
    dropped = {}
    for g in games:
        if not all(_covered(g, x) for x in sources.values()):
            who = [n for n, x in sources.items() if not _covered(g, x)]
            dropped.setdefault(g["season"], []).append("/".join(who))
    for season, who in sorted(dropped.items()):
        print(f"  {season}: {len(who)} game(s) dropped, no xG in {sorted(set(who))}")
    if len(games) - len(keep) > 0.01 * len(games):
        raise ValueError(f"{len(games) - len(keep)} of {len(games)} games lack xG in some "
                         f"source; more than 1% means a source is broken")
    return keep


def _any_score_5v5(xg_data):
    """MoneyPuck totals with xgf_adj/xga_adj swapped for 5v5 at any score."""
    return {gid: {t: {**v, "xgf_adj": v["xgf5"], "xga_adj": v["xga5"]} for t, v in teams.items()}
            for gid, teams in xg_data.items()}


def _rows(games, xg_data):
    """Point-in-time rows for every game (min_gp=0, so early games are kept)."""
    return hd.build_point_in_time_rows(games, min_gp=0, starters=None, xg_data=xg_data,
                                       xg_required_seasons=frozenset())


def _fit_score(train, test, columns, C=0.1):
    X = np.array([[float(r[c]) for c in columns] for r in train])
    y = np.array([int(r["home_win"]) for r in train])
    Xt = np.array([[float(r[c]) for c in columns] for r in test])
    yt = np.array([int(r["home_win"]) for r in test])
    scaler = StandardScaler().fit(X)
    model = LogisticRegression(max_iter=2000, C=C, solver="liblinear").fit(scaler.transform(X), y)
    p = model.predict_proba(scaler.transform(Xt))[:, 1]
    return {"n": len(test), "log_loss": log_loss(yt, p, labels=[0, 1]),
            "brier": brier_score_loss(yt, p), "accuracy": accuracy_score(yt, p > 0.5)}


def _constant(train, test):
    p = np.mean([int(r["home_win"]) for r in train])
    yt = np.array([int(r["home_win"]) for r in test])
    q = np.full(len(yt), p)
    return {"n": len(test), "log_loss": log_loss(yt, q, labels=[0, 1]),
            "brier": brier_score_loss(yt, q), "accuracy": accuracy_score(yt, q > 0.5)}


# --------------------------------------------------------------------------- #
# 1. Source                                                                    #
# --------------------------------------------------------------------------- #
def source_comparison(row_sets, elo_by_id):
    """row_sets: {name: (rows, columns)}; every rows list covers the same games."""
    def mature(rows):
        return [r for r in rows if r["home_gp"] >= EARLY_GP and r["away_gp"] >= EARLY_GP]

    names = list(row_sets)
    results = {"shipped_split": {}, "loso": {n: {} for n in names + ["elo"]}}

    ref = mature(row_sets[names[0]][0])
    elo_rows = [elo_by_id[int(r["game_id"])] for r in ref]

    def split(rows, test_season, train_seasons=None):
        tr = [r for r in rows if r["season"] != test_season
              and (train_seasons is None or r["season"] in train_seasons)]
        return tr, [r for r in rows if r["season"] == test_season]

    for name, (rows, cols) in row_sets.items():
        tr, te = split(mature(rows), SHIPPED_TEST, SHIPPED_TRAIN)
        results["shipped_split"][name] = _fit_score(tr, te, cols)
    tr, te = split(elo_rows, SHIPPED_TEST, SHIPPED_TRAIN)
    results["shipped_split"]["elo"] = _fit_score(tr, te, ELO_COLUMNS, C=1.0)

    for s in SEASONS:
        for name, (rows, cols) in row_sets.items():
            tr, te = split(mature(rows), s)
            results["loso"][name][s] = _fit_score(tr, te, cols)
        tr, te = split(elo_rows, s)
        results["loso"]["elo"][s] = _fit_score(tr, te, ELO_COLUMNS, C=1.0)
    return results


# --------------------------------------------------------------------------- #
# 2. Early season                                                              #
# --------------------------------------------------------------------------- #
def season_xg5_share(highslot_file=HIGHSLOT_XG_PATH):
    """{(season_str, team): 5v5 xG share over that regular season}."""
    games = json.loads(highslot_file.read_text())["games"]
    tot = {}
    for gid, teams in games.items():
        year = int(gid) // 1_000_000
        season = f"{year}{year + 1}"
        for team, v in teams.items():
            f, a = tot.get((season, team), (0.0, 0.0))
            tot[(season, team)] = (f + v["xgf5"], a + v["xga5"])
    return {k: f / (f + a) for k, (f, a) in tot.items() if f + a > 0}


def _prior(shares, season, team):
    prev = f"{int(season[:4]) - 1}{int(season[:4])}"
    for code in (team, PRIOR_ALIASES.get(team)):
        if code and (prev, code) in shares:
            return shares[(prev, code)], True
    return 0.5, False


def early_season(hs5_rows, elo_by_id, shares):
    early = []
    no_prior = 0
    for r in hs5_rows:
        if r["home_gp"] >= EARLY_GP and r["away_gp"] >= EARLY_GP:
            continue
        hp, h_ok = _prior(shares, r["season"], r["home_team"])
        ap, a_ok = _prior(shares, r["season"], r["away_team"])
        no_prior += (not h_ok) + (not a_ok)
        e = elo_by_id[int(r["game_id"])]
        # In-season 5v5 xG differential so far, shrunk toward 0 by games
        # played, so the model can lean on it as it accumulates.
        def cur(side):
            gp = r[f"{side}_gp"]
            rate = float(r[f"{side}_xgf_per60"]) - float(r[f"{side}_xga_per60"])
            return rate * gp / (gp + 3) if gp else 0.0
        early.append({**{k: r[k] for k in ("season", "home_win", "rest_diff", "home_b2b", "away_b2b")},
                      "elo_diff": e["elo_diff"], "prior_diff": hp - ap,
                      "cur_diff": cur("home") - cur("away")})

    rest = ["rest_diff", "home_b2b", "away_b2b"]
    candidates = {
        "elo (served today)": ELO_COLUMNS,
        "prior": ["prior_diff"] + rest,
        "prior + in-season xG": ["prior_diff", "cur_diff"] + rest,
        "elo + prior": ["elo_diff", "prior_diff"] + rest,
        "elo + prior + in-season xG": ["elo_diff", "prior_diff", "cur_diff"] + rest,
    }
    out = {"n_games": len(early), "team_slots_without_prior": no_prior,
           "loso": {n: {} for n in ["home constant"] + list(candidates)}}
    for s in SEASONS:
        tr = [r for r in early if r["season"] != s]
        te = [r for r in early if r["season"] == s]
        out["loso"]["home constant"][s] = _constant(tr, te)
        for name, cols in candidates.items():
            out["loso"][name][s] = _fit_score(tr, te, cols, C=1.0)
    return out


# --------------------------------------------------------------------------- #
# Report                                                                       #
# --------------------------------------------------------------------------- #
def _pooled(per_season, skip=ANOMALOUS_LOSO_SEASONS):
    """Game-weighted means over seasons, leaving out the anomalous ones."""
    vals = [v for s, v in per_season.items() if s not in skip]
    n = sum(v["n"] for v in vals)
    return {"n": n, **{m: sum(v[m] * v["n"] for v in vals) / n
                       for m in ("log_loss", "brier", "accuracy")}}


def _table(title, rows):
    print(f"\n{title}")
    print(f"  {'':<30}{'n':>6}{'log loss':>10}{'Brier':>9}{'acc':>7}")
    for name, r in rows.items():
        print(f"  {name:<30}{r['n']:>6}{r['log_loss']:>10.4f}{r['brier']:>9.4f}{r['accuracy']:>7.3f}")


def _season_wins(loso, a, b):
    """Seasons (non-anomalous) where `a` beats `b` on both log loss and Brier."""
    seasons = [s for s in SEASONS if s not in ANOMALOUS_LOSO_SEASONS]
    wins = sum(1 for s in seasons if loso[a][s]["log_loss"] < loso[b][s]["log_loss"]
               and loso[a][s]["brier"] < loso[b][s]["brier"])
    return wins, len(seasons)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", default=None, help="also write the results here")
    a = ap.parse_args()

    print("Loading schedules, MoneyPuck and High Slot xG (cached)...")
    sources = {"MoneyPuck": load_moneypuck_xg(SEASONS),
               "High Slot": load_highslot_xg(SEASONS, "close")}
    games = _common_games(_games(), sources)
    row_sets = {
        "mp": (_rows(games, sources["MoneyPuck"]), SHIPPED_COLUMNS),
        "hs": (_rows(games, sources["High Slot"]), SHIPPED_COLUMNS),
        "hs5": (_rows(games, load_highslot_xg(SEASONS, "ev5")), NO_HD_COLUMNS),
    }
    row_sets["mp5"] = (_rows(games, _any_score_5v5(sources["MoneyPuck"])), NO_HD_COLUMNS)
    row_sets["mp-hd"] = (row_sets["mp"][0], NO_HD_COLUMNS)
    row_sets["hs-hd"] = (row_sets["hs"][0], NO_HD_COLUMNS)
    row_sets = {k: row_sets[k] for k in ("mp", "mp-hd", "mp5", "hs", "hs-hd", "hs5")}

    elo_rows = _attach_elo_from_games(row_sets["mp"][0], games)
    elo_by_id = {r["game_id"]: r for r in elo_rows}

    src = source_comparison(row_sets, elo_by_id)
    early = early_season(row_sets["hs5"][0], elo_by_id, season_xg5_share())

    _table(f"1. SOURCE, shipped split (train {SHIPPED_TRAIN[0]}..{SHIPPED_TRAIN[-1]}, "
           f"test {SHIPPED_TEST})", src["shipped_split"])
    _table("1. SOURCE, leave-one-season-out 2018-19..2025-26, pooled "
           "(2019-20 and 2020-21 left out)", {n: _pooled(v) for n, v in src["loso"].items()})
    print("\n  Seasons won on both metrics (of 6 normal seasons):")
    for x, y in (("hs", "mp"), ("hs-hd", "mp-hd"), ("hs5", "mp5"), ("hs5", "mp"),
                 ("mp5", "mp"), ("mp", "elo"), ("hs5", "elo")):
        w, n = _season_wins(src["loso"], x, y)
        print(f"    {x:>6} over {y:<6} {w}/{n}")

    _table(f"2. EARLY SEASON (either team under {EARLY_GP} GP), leave-one-season-out, pooled "
           f"({early['n_games']} games, {early['team_slots_without_prior']} team-games "
           f"without a prior)", {n: _pooled(v) for n, v in early["loso"].items()})
    print("\n  Seasons won on both metrics vs elo (of 6 normal seasons):")
    for name in early["loso"]:
        if name != "elo (served today)":
            w, n = _season_wins(early["loso"], name, "elo (served today)")
            print(f"    {name:<28} {w}/{n}")

    if a.json:
        with open(a.json, "w") as f:
            json.dump({"source": src, "early_season": early}, f, indent=1)
        print(f"\nwrote {a.json}")


if __name__ == "__main__":
    main()
