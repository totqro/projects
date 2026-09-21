"""Stage 3b: is the efficiency signal weak, or is the tracker? Compare the
season-mean+prior tracker against an EWMA-over-games variant (with a season
discount), scored alone and on top of Elo."""
import sys, pathlib, json, time, itertools
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np, pandas as pd
from src.data import nflverse as nv
from src.data.team_games import normalize_games, build_team_games, build_qb_games
from src.features.engine import FeatureEngine
from src.features import efficiency as effmod
from src.features.efficiency import EfficiencyTracker, _all_keys, _game_values
from src.models.loso import loso_win, fmt, beats

class EWMATracker(EfficiencyTracker):
    """rating = (n0*league_mean + sum w_i * adj_i) / (n0 + sum w_i), w_i = lam^(games ago) * sdisc^(seasons ago)."""
    def __init__(self, lam=0.9, sdisc=0.6, n0=3.0):
        super().__init__(n0=n0, carry=0.0)
        self.lam, self.sdisc = lam, sdisc
        self.all_games = {}   # team -> list of (season, adj dict)
    def _ensure_season(self, team, season):
        if self.team_season.get(team) == season: return
        if team not in self.ratings: self.ratings[team] = dict(self._league_mean_snapshot()); self.all_games[team] = []
        self.team_season[team] = season; self.season_games[team] = []; self.season_raw[team] = []
        self._recompute(team, season)
    def _recompute(self, team, season):
        lm = self._league_mean_snapshot() if self.ratings else {k: 0.0 for k in _all_keys()}
        hist = self.all_games.get(team, [])
        new = {}
        for key in _all_keys():
            wsum, vsum = self.n0, self.n0 * lm[key]
            for i, (s, adj) in enumerate(reversed(hist)):
                w = (self.lam ** i) * (self.sdisc ** (season - s))
                wsum += w; vsum += w * adj[key]
            new[key] = vsum / wsum
        self.ratings[team] = new
    def update_week(self, wk_games, wk_team_games):
        if wk_team_games.empty: return
        season = int(wk_team_games.season.iloc[0])
        pre = {t: dict(self.rating(t, season)) for t in set(wk_team_games.team) | set(wk_team_games.opp)}
        lm = dict(self.league_mean)
        for r in wk_team_games.to_dict("records"):
            raw = _game_values(r); adj = {}
            for (side, name), val in raw.items():
                mirror = ("def", name) if side == "off" else ("off", name)
                adj[(side, name)] = val - (pre[r["opp"]][mirror] - lm[mirror])
            self.all_games[r["team"]].append((season, adj)); self.season_games[r["team"]].append(adj); self.season_raw[r["team"]].append(raw)
        for t in set(wk_team_games.team): self._recompute(t, season)
        self.league_mean = self._league_mean_snapshot()

games = normalize_games(nv.feature_frame(nv.load_games(range(2014, 2024)))); games = games[games.home_score.notna()].copy()
tg = build_team_games(games); qbg = build_qb_games(games); players = nv.load_players()
e0 = json.load(open("data/processed/stage0_elo_params.json")); q1 = json.load(open("data/processed/stage1_qb_params.json"))
elo_params = {"k": q1["k"], "hfa": e0["hfa"], "reversion": e0["reversion"]}; qb_params = {"n0": q1["n0"], "decay": q1["decay"]}; scale = q1["qb_elo_scale"]
gi = games.set_index("game_id")
def finish(f):
    f = f[f.season.isin(nv.TRAIN_SEASONS)].copy()
    hs, as_ = gi.loc[f.game_id, "home_score"].to_numpy(), gi.loc[f.game_id, "away_score"].to_numpy()
    f["home_win"] = (hs > as_).astype(int); return f[hs != as_]
rows = []
for lam, sdisc, n0 in itertools.product([0.85, 0.9, 0.95, 0.98], [0.4, 0.6, 0.8], [1, 3, 6]):
    eng = FeatureEngine(elo_params=elo_params, qb_params=qb_params, qb_elo_scale=scale, players=players, efficiency=EWMATracker(lam, sdisc, n0))
    f = finish(eng.run(games, tg, qbg))
    r = loso_win(f, ["elo_diff", "epa_margin_diff"], C=1.0); r2 = loso_win(f, ["epa_margin_diff"], C=1.0)
    r3 = loso_win(f, ["epa_margin_diff", "pass_epa_margin_diff", "success_margin_diff", "st_epa_diff", "qb_epa_diff"], C=0.3)
    rows.append({"lam": lam, "sdisc": sdisc, "n0": n0, "ll_with_elo": r["log_loss"], "brier_with_elo": r["brier"], "ll_alone": r2["log_loss"], "ll_eff_bundle": r3["log_loss"]})
    print(rows[-1], flush=True)
res = pd.DataFrame(rows); print(res.sort_values("ll_with_elo").head(8).to_string(index=False)); print(res.sort_values("ll_alone").head(5).to_string(index=False))
res.to_csv("data/processed/stage3b_ewma.csv", index=False)
