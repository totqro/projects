"""Point-in-time rows 2014-15..2025-26 (2014-15 is warm-up only: it seeds
goalie history, head-to-head and Elo for 2015-16), plus pregame elo_diff.
Run from nhllines/. Writes the CSV given as argv[1]."""
import csv, sys
sys.path.insert(0, ".")
import src.data.historical_dataset as hd
from src.models.elo_baseline import compute_pregame_elo

out = sys.argv[1]
seasons = [f"{y}{y + 1}" for y in range(2014, 2026)]
hd.MONEYPUCK_SEASONS = frozenset(seasons)

all_games = []
for s in seasons:
    g = hd.fetch_season_games_full(s, verbose=False)
    print(f"{s}: {len(g)} games", flush=True)
    all_games.extend(g)

print("starting goalies...", flush=True)
starters = None if "--no-goalies" in sys.argv else hd.fetch_all_starters(all_games, verbose=True)

print("xG...", flush=True)
xg, coverage = hd.load_game_xg(all_games, seasons, verbose=True)
for s, (n, t) in sorted(coverage.items()):
    print(f"  xG coverage {s}: {n}/{t}", flush=True)
covered = {gid for gid, teams in xg.items()}
games = [g for g in all_games if g["id"] in xg
         and g["home_team"] in xg[g["id"]] and g["away_team"] in xg[g["id"]]]
print(f"dropped {len(all_games) - len(games)} games without xG", flush=True)

rows = hd.build_point_in_time_rows(games, min_gp=0, starters=starters, xg_data=xg,
                                   xg_required_seasons=frozenset())
elo = compute_pregame_elo(all_games)
for r in rows:
    h, a = elo[int(r["game_id"])]
    r["elo_diff"] = h - a
with open(out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
print(f"wrote {len(rows)} rows -> {out}", flush=True)
