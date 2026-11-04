"""Shared evaluation for the feature search.

Yardstick (the only number searches may look at): leave-one-season-out over
2015-16..2023-24. Each fold trains on the other CV seasons and scores the
held-out one; the score is pooled log loss over the 7 normal seasons
(2019-20 and 2020-21 are trained on but not scored, as in model_gate.py).
2024-25 and 2025-26 are locked: only final.py touches them.

Rows: both teams >= 5 GP (the regime the xG model serves in production).
Model: L2 logistic on standardised features, C=0.1 (the shipped settings),
fit by Newton's method so a candidate scores in milliseconds."""
import csv, os
from pathlib import Path
import numpy as np

HERE = Path(__file__).parent
NO_GOALIE = os.environ.get("NO_GOALIE") == "1"
DATA = HERE / "data" / ("rows_nogoalie.csv" if NO_GOALIE else "rows_2015_2026.csv")
CV_SEASONS = [f"{y}{y + 1}" for y in range(2015, 2024)]
SCORED = [s for s in CV_SEASONS if s not in ("20192020", "20202021")]
TEST_SEASONS = ["20242025", "20252026"]
MIN_GP = 5
C = 0.1

GOALIE = ["home_goalie_starts", "home_goalie_sv_pct", "home_goalie_gaa", "home_goalie_recent_sv_pct",
          "away_goalie_starts", "away_goalie_sv_pct", "away_goalie_gaa", "away_goalie_recent_sv_pct",
          "goalie_sv_pct_diff", "goalie_recent_sv_pct_diff", "goalie_experience_diff"]
SHIPPED = ["home_gp", "home_win_pct", "home_points_pct", "home_gf_pg", "home_ga_pg",
           "home_home_win_pct", "home_form_win_pct", "home_form_gf", "home_form_ga",
           "home_rest_days", "home_b2b", "home_streak", "home_trend",
           "away_gp", "away_win_pct", "away_points_pct", "away_gf_pg", "away_ga_pg",
           "away_road_win_pct", "away_form_win_pct", "away_form_gf", "away_form_ga",
           "away_rest_days", "away_b2b", "away_streak", "away_trend",
           "home_xgf_per60", "home_xga_per60", "home_high_danger_xg_share",
           "home_xg_luck_for", "home_xg_luck_against",
           "away_xgf_per60", "away_xga_per60", "away_high_danger_xg_share",
           "away_xg_luck_for", "away_xg_luck_against",
           "win_pct_diff", "points_pct_diff", "form_diff", "goal_diff_rate_diff",
           "xg_diff_rate_diff", "rest_diff", "h2h_home_win_rate", "h2h_meetings"]
ELO = ["elo_diff", "rest_diff", "home_b2b", "away_b2b"]
# Engineered differences the raw set lacks (all from point-in-time columns).
ENGINEERED = {
    "xgf_diff": lambda r: r["home_xgf_per60"] - r["away_xgf_per60"],
    "xga_diff": lambda r: r["home_xga_per60"] - r["away_xga_per60"],
    "hd_share_diff": lambda r: r["home_high_danger_xg_share"] - r["away_high_danger_xg_share"],
    "xg_luck_net_diff": lambda r: (r["home_xg_luck_for"] - r["home_xg_luck_against"])
                                  - (r["away_xg_luck_for"] - r["away_xg_luck_against"]),
    "form_goal_diff": lambda r: (r["home_form_gf"] - r["home_form_ga"])
                                - (r["away_form_gf"] - r["away_form_ga"]),
    "venue_win_pct_diff": lambda r: r["home_home_win_pct"] - r["away_road_win_pct"],
    "streak_diff": lambda r: r["home_streak"] - r["away_streak"],
    "goalie_gaa_diff": lambda r: r["home_goalie_gaa"] - r["away_goalie_gaa"],
}
ALL = list(dict.fromkeys(SHIPPED + GOALIE + ["elo_diff"] + list(ENGINEERED)))
if NO_GOALIE:
    ALL = [c for c in ALL if c not in GOALIE and c != "goalie_gaa_diff"]


def load(min_gp=MIN_GP):
    rows = []
    with open(DATA) as f:
        for r in csv.DictReader(f):
            if r["season"] not in CV_SEASONS + TEST_SEASONS:
                continue
            d = {k: float(r[k]) for k in SHIPPED + GOALIE + ["elo_diff", "home_win"]}
            if min(d["home_gp"], d["away_gp"]) < min_gp:
                continue
            for k, fn in ENGINEERED.items():
                d[k] = fn(d)
            d["season"] = r["season"]
            d["date"] = r["date"]
            rows.append(d)
    X = np.array([[r[k] for k in ALL] for r in rows])
    y = np.array([r["home_win"] for r in rows])
    season = np.array([r["season"] for r in rows])
    return X, y, season


def fit(Xs, y, C=C, iters=25):
    """L2 logistic: minimise C*sum(logloss) + 0.5*|w|^2 (intercept unpenalised)."""
    n, p = Xs.shape
    A = np.hstack([np.ones((n, 1)), Xs])
    beta = np.zeros(p + 1)
    reg = np.full(p + 1, 1.0 / C); reg[0] = 0.0
    for _ in range(iters):
        z = A @ beta
        mu = 1 / (1 + np.exp(-z))
        g = A.T @ (mu - y) + reg * beta
        H = (A * (mu * (1 - mu))[:, None]).T @ A + np.diag(reg)
        step = np.linalg.solve(H, g)
        beta -= step
        if np.abs(step).max() < 1e-8:
            break
    return beta


def predict(beta, Xs):
    return 1 / (1 + np.exp(-(beta[0] + Xs @ beta[1:])))


def logloss(p, y):
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


class Evaluator:
    """Precomputes per-fold standardised matrices so a subset is a column slice."""

    def __init__(self, C=C):
        X, y, season = load()
        self.C = C
        self.cols = ALL
        self.idx = {c: i for i, c in enumerate(ALL)}
        self.folds = []
        cv = np.isin(season, CV_SEASONS)
        for s in CV_SEASONS:
            tr, te = cv & (season != s), season == s
            mu, sd = X[tr].mean(0), X[tr].std(0)
            sd[sd == 0] = 1
            self.folds.append((s, (X[tr] - mu) / sd, y[tr], (X[te] - mu) / sd, y[te]))
        self.X, self.y, self.season = X, y, season
        self.cache = {}

    def score(self, feats, C=None, detail=False):
        """Pooled LOSO log loss over the 7 normal CV seasons (lower is better)."""
        key = (frozenset(feats), C)
        if key in self.cache and not detail:
            return self.cache[key]
        j = [self.idx[f] for f in feats]
        losses, per, briers, hits = [], {}, [], []
        for s, Xtr, ytr, Xte, yte in self.folds:
            if s not in SCORED and not detail:
                continue
            b = fit(Xtr[:, j], ytr, C or self.C)
            p = predict(b, Xte[:, j])
            ll = logloss(p, yte)
            per[s] = (ll.mean(), np.mean((p - yte) ** 2), np.mean((p > .5) == yte), len(yte))
            if s in SCORED:
                losses.append(ll); briers.append((p - yte) ** 2); hits.append((p > .5) == yte)
        out = float(np.concatenate(losses).mean())
        self.cache[key] = out
        if detail:
            return {"logloss": out, "brier": float(np.concatenate(briers).mean()),
                    "acc": float(np.concatenate(hits).mean()),
                    "n": int(sum(len(h) for h in hits)), "per_season": per}
        return out

    def per_game(self, feats, C=None):
        """Per-game log loss on the scored seasons (for paired bootstraps)."""
        j = [self.idx[f] for f in feats]
        out = []
        for s, Xtr, ytr, Xte, yte in self.folds:
            if s in SCORED:
                out.append(logloss(predict(fit(Xtr[:, j], ytr, C or self.C), Xte[:, j]), yte))
        return np.concatenate(out)
