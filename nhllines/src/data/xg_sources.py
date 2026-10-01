"""
Per-game team xG from whichever source has it.

MoneyPuck first (the production model was originally fit on its xG), then
NHL API play-by-play scored with the repo's own xG model (nhl_pbp_xg.py) for
any game MoneyPuck doesn't cover: a season it hasn't posted, a lagging
in-progress season, or MoneyPuck being down entirely. Training, serving and
the playoff bracket all go through here, so they see the same numbers.
"""

from .moneypuck_data import load_moneypuck_xg
from .nhl_pbp_xg import load_pbp_xg


def load_game_xg(games: list, seasons: list, verbose: bool = True) -> tuple:
    """
    Returns (xg_data, coverage):
      xg_data:  {nhl_game_id: {team_abbrev: {...}}}
      coverage: {season: (games_with_xg, games_total)}
    Only games whose season is in `seasons` are looked up. Never raises on a
    source being unavailable; callers decide what coverage is acceptable.
    """
    seasons = sorted(set(seasons))
    wanted = [g for g in games if g["season"] in seasons]
    xg_data = load_moneypuck_xg(seasons, strict=False)

    missing = [g["id"] for g in wanted if g["id"] not in xg_data]
    if missing:
        if verbose:
            print(f"  {len(missing)} of {len(wanted)} games not in MoneyPuck, "
                  f"scoring them from NHL play-by-play")
        xg_data.update(load_pbp_xg(missing))

    # Covered means both of the schedule's team codes are in the xG entry:
    # a code mismatch would otherwise count as covered but join to nothing.
    def covered(g):
        teams = xg_data.get(g["id"]) or {}
        return g["home_team"] in teams and g["away_team"] in teams

    coverage = {}
    for s in seasons:
        season_games = [g for g in wanted if g["season"] == s]
        coverage[s] = (sum(1 for g in season_games if covered(g)), len(season_games))
    return xg_data, coverage
