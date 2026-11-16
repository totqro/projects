"""
Season projections: a per-game win model and a Monte Carlo of the rest of
the season, shared by the offline fit (fit_projections.py) and the nightly
run (nhl_projections.py).

The win model is core4 (nhllines/feature_search: Elo, xG differential and
both teams' back-to-backs), refit on High Slot's own 5v5 xG so the site can
serve it from its own game index:

    logit P(home win) = b0 + b1*elo_diff + b2*xgd_diff + b3*home_b2b + b4*away_b2b

    elo_diff   home Elo - away Elo (K=6, a third back to 1500 each summer,
               no home edge inside Elo: b0 carries home ice)
    xgd_diff   each team's season-to-date 5v5 xG differential per game, home
               minus away
    *_b2b      played the day before, 0/1

Until both teams have MIN_GP games, the "early" model (the same without
xgd_diff) is used, as core4's shadow does.

A simulated game goes to overtime at the league's rate; the stronger team's
edge shrinks in overtime and the shootout (slope OT_K), and the overall win
probability is kept equal to the model's. Each simulated season also draws a
strength offset per team (SIGMA on the logit scale): a team's xG and Elo
after 15 games are estimates, and a season with fixed probabilities gives
ranges that are too narrow. SIGMA is chosen by the back-test.

Ranking: points, then regulation wins, regulation + overtime wins, wins,
goal differential, then a coin flip (the NHL's head-to-head step is left
out). Playoffs: top three in each division plus two wild cards per
conference.
"""

import numpy as np

INITIAL_ELO = 1500.0
ELO_K = 6.0
ELO_REVERSION = 1.0 / 3.0
MIN_GP = 5

ATLANTIC = ["BOS", "BUF", "DET", "FLA", "MTL", "OTT", "TBL", "TOR"]
METRO = ["CAR", "CBJ", "NJD", "NYI", "NYR", "PHI", "PIT", "WSH"]


def alignment(start_year: int) -> dict:
    """{team: (conference, division)} for the season starting in start_year.
    2020-21's temporary divisions are not covered (its playoffs had a
    different format); every other season since 2014-15 is."""
    if start_year == 2020:
        raise ValueError("2020-21 used temporary divisions; not supported")
    central = ["CHI", "COL", "DAL", "MIN", "NSH", "STL", "WPG"]
    pacific = ["ANA", "CGY", "EDM", "LAK", "SJS", "VAN"]
    if start_year >= 2017:
        pacific.append("VGK")
    if start_year >= 2021:
        pacific.append("SEA")
        central.append("UTA" if start_year >= 2024 else "ARI")
    else:
        pacific.append("ARI")
    out = {}
    for conf, div, teams in (("East", "Atlantic", ATLANTIC), ("East", "Metropolitan", METRO),
                             ("West", "Central", central), ("West", "Pacific", pacific)):
        for t in teams:
            out[t] = (conf, div)
    return out


def season_of(game_id) -> int:
    """NHL game ids start with the season's start year."""
    return int(str(game_id)[:4])


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


# --------------------------------------------------------------------- Elo

class Elo:
    """Walks results in order. Ratings are pregame for each team's next game."""

    def __init__(self, ratings=None, season=None):
        self.ratings = dict(ratings or {})
        self.season = {t: season for t in self.ratings}

    def rating(self, team, season):
        r = self.ratings.get(team, INITIAL_ELO)
        if team in self.ratings and self.season.get(team) != season:
            r += (INITIAL_ELO - r) * ELO_REVERSION
        return r

    def update(self, home, away, home_won, season):
        h, a = self.rating(home, season), self.rating(away, season)
        delta = ELO_K * ((1.0 if home_won else 0.0) - 1.0 / (1.0 + 10 ** (-(h - a) / 400.0)))
        self.ratings[home], self.ratings[away] = h + delta, a - delta
        self.season[home] = self.season[away] = season

    def snapshot(self, season):
        """Every team's rating carried into `season` (reverted if they have
        not played in it yet)."""
        return {t: self.rating(t, season) for t in self.ratings}


# ------------------------------------------------------------- the model

def game_logit(model: dict, elo_diff, xgd_diff, home_b2b, away_b2b, early):
    """Logit of P(home win). `early` (bool or array) picks the Elo-only model."""
    c, e = model["core"], model["early"]
    core = (c["intercept"] + c["elo_diff"] * elo_diff + c["xgd_diff"] * xgd_diff
            + c["home_b2b"] * home_b2b + c["away_b2b"] * away_b2b)
    elo = e["intercept"] + e["elo_diff"] * elo_diff + e["home_b2b"] * home_b2b + e["away_b2b"] * away_b2b
    return np.where(early, elo, core)


class Tally:
    """A team's record so far: what the standings and tiebreakers need."""
    __slots__ = ("gp", "w", "l", "otl", "rw", "row", "gf", "ga", "xgd_sum", "xg_gp")

    def __init__(self):
        self.gp = self.w = self.l = self.otl = self.rw = self.row = self.gf = self.ga = 0
        self.xgd_sum = 0.0
        self.xg_gp = 0

    @property
    def pts(self):
        return 2 * self.w + self.otl

    @property
    def xgd(self):
        return self.xgd_sum / self.xg_gp if self.xg_gp else 0.0

    def add(self, gf, ga, end, xgf5=None, xga5=None):
        self.gp += 1
        self.gf += gf
        self.ga += ga
        if gf > ga:
            self.w += 1
            self.rw += end == "REG"
            self.row += end != "SO"
        elif end == "REG":
            self.l += 1
        else:
            self.otl += 1
        if xgf5 is not None and xga5 is not None:
            self.xgd_sum += xgf5 - xga5
            self.xg_gp += 1


def record_game(tallies: dict, g: dict):
    """g: {home, away, hs, as, end, hx5?, ax5?}"""
    hx, ax = g.get("hx5"), g.get("ax5")
    tallies.setdefault(g["home"], Tally()).add(g["hs"], g["as"], g["end"], hx, ax)
    tallies.setdefault(g["away"], Tally()).add(g["as"], g["hs"], g["end"], ax, hx)


def b2b_flags(dates_by_team: dict, team: str, date: str) -> float:
    """1.0 if `team` has a game the day before `date` (ISO dates)."""
    from datetime import date as D, timedelta
    prev = (D.fromisoformat(date) - timedelta(days=1)).isoformat()
    return 1.0 if prev in dates_by_team.get(team, ()) else 0.0


# --------------------------------------------------------------- simulate

def simulate(model: dict, align: dict, tallies: dict, remaining: list, elo: dict,
             n: int = 10000, sigma: float = None, seed: int = 0, dates_by_team: dict = None):
    """
    Play out `remaining` [{home, away, date}] n times from `tallies`.
    Team strength going forward: current Elo and season-to-date 5v5 xG
    differential, both held fixed, plus a per-season draw of N(0, sigma).
    Returns (teams, results) with results arrays shaped (n, teams).
    """
    sigma = model["sigma"] if sigma is None else sigma
    rng = np.random.default_rng(seed)
    teams = sorted(align)
    ix = {t: i for i, t in enumerate(teams)}
    T = len(teams)
    zero = Tally()
    tal = [tallies.get(t, zero) for t in teams]

    pts = np.tile(np.array([t.pts for t in tal], np.int32), (n, 1))
    w = np.tile(np.array([t.w for t in tal], np.int32), (n, 1))
    rw = np.tile(np.array([t.rw for t in tal], np.int32), (n, 1))
    row = np.tile(np.array([t.row for t in tal], np.int32), (n, 1))
    gd = np.tile(np.array([t.gf - t.ga for t in tal], np.int32), (n, 1))

    if remaining:
        dates_by_team = dates_by_team or {}
        h = np.array([ix[g["home"]] for g in remaining])
        a = np.array([ix[g["away"]] for g in remaining])
        elo_arr = np.array([elo.get(t, INITIAL_ELO) for t in teams])
        xgd = np.array([t.xgd for t in tal])
        xg_gp = np.array([t.xg_gp for t in tal])
        hb = np.array([b2b_flags(dates_by_team, g["home"], g["date"]) for g in remaining])
        ab = np.array([b2b_flags(dates_by_team, g["away"], g["date"]) for g in remaining])
        early = (xg_gp[h] < MIN_GP) | (xg_gp[a] < MIN_GP)
        base = game_logit(model, elo_arr[h] - elo_arr[a], xgd[h] - xgd[a], hb, ab, early)

        eps = rng.normal(0.0, sigma, (n, T)) if sigma > 0 else np.zeros((n, T))
        ot = model["ot"]
        margins = np.asarray(model["margins"], float)
        margins = margins / margins.sum()
        cum_margin = np.cumsum(margins)
        for gi in range(len(remaining)):
            hi, ai = h[gi], a[gi]
            p = sigmoid(base[gi] + eps[:, hi] - eps[:, ai])
            q = 0.5 + ot["k"] * (p - 0.5)             # P(home wins | extra time)
            p_ot = ot["rate"]
            p_reg_home = np.clip(p - p_ot * q, 0.0, 1.0)
            u = rng.random(n)
            reg_home = u < p_reg_home
            ot_home = (u >= p_reg_home) & (u < p_reg_home + p_ot * q)
            ot_away = (u >= p_reg_home + p_ot * q) & (u < p_reg_home + p_ot)
            reg_away = ~(reg_home | ot_home | ot_away)
            home_won = reg_home | ot_home
            extra = ot_home | ot_away
            so = extra & (rng.random(n) < ot["so_share"])
            m = np.where(extra, 1, 1 + np.searchsorted(cum_margin, rng.random(n)))
            pts[:, hi] += np.where(home_won, 2, extra.astype(np.int32))
            pts[:, ai] += np.where(~home_won, 2, extra.astype(np.int32))
            w[:, hi] += home_won
            w[:, ai] += ~home_won
            rw[:, hi] += reg_home
            rw[:, ai] += reg_away
            row[:, hi] += home_won & ~so
            row[:, ai] += ~home_won & ~so
            signed = np.where(home_won, m, -m)
            gd[:, hi] += signed
            gd[:, ai] -= signed

    # One sortable number per team per season; the last digit is a coin flip.
    key = (pts.astype(np.float64) * 1e10 + rw * 1e8 + row * 1e6 + w * 1e4
           + (gd + 400) * 10 + rng.integers(0, 10, (n, T)))
    playoff, divwin = qualify(key, teams, align)
    pres = key == key.max(axis=1, keepdims=True)
    return teams, {"pts": pts, "playoff": playoff, "divwin": divwin, "pres": pres, "key": key}


def _rank(sub):
    """Rank (0 = best) along axis 1 of larger-is-better keys."""
    return np.argsort(np.argsort(-sub, axis=1), axis=1)


def qualify(key: np.ndarray, teams: list, align: dict):
    """Top three in each division, then two wild cards per conference."""
    n, T = key.shape
    playoff = np.zeros((n, T), bool)
    divwin = np.zeros((n, T), bool)
    divs = sorted(set(align.values()))
    for d in divs:
        idx = [i for i, t in enumerate(teams) if align[t] == d]
        r = _rank(key[:, idx])
        playoff[:, idx] = r < 3
        divwin[:, idx] = r == 0
    for conf in sorted(set(c for c, _ in divs)):
        idx = [i for i, t in enumerate(teams) if align[t][0] == conf]
        sub = np.where(playoff[:, idx], -np.inf, key[:, idx])
        playoff[:, idx] |= _rank(sub) < 2
    return playoff, divwin


def summarize(teams, res, align, tallies):
    """Per-team summary of a simulation, for the site."""
    out = []
    pts = res["pts"]
    zero = Tally()
    for i, t in enumerate(teams):
        tl = tallies.get(t, zero)
        col = pts[:, i]
        lo, hi = np.percentile(col, [10, 90])
        cmin, cmax = int(col.min()), int(col.max())
        hist = np.bincount(col - cmin, minlength=cmax - cmin + 1)
        out.append({
            "team": t, "conf": align[t][0], "div": align[t][1],
            "gp": tl.gp, "w": tl.w, "l": tl.l, "otl": tl.otl, "pts": tl.pts,
            "proj": round(float(col.mean()), 1), "lo": int(round(lo)), "hi": int(round(hi)),
            "playoff": round(float(res["playoff"][:, i].mean()), 4),
            "divwin": round(float(res["divwin"][:, i].mean()), 4),
            "pres": round(float(res["pres"][:, i].mean()), 4),
            "hist": [cmin, hist.tolist()],
        })
    return out
