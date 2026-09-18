"""
Does offseason roster change (net gameScore swing) actually predict what
happens to a team's record? The real validation step roster_turnover.py's
own docstring has been flagging as not-yet-done since it was built.
=====================================================================
For every team across the two most recent completed offseasons
(2023-24->2024-25, 2024-25->2025-26), this joins roster_turnover.py's net
gameScore change to the team's ACTUAL points change between the two seasons,
and reports:

  1. The biggest buyers and sellers each offseason, with what actually
     happened to their record — not just the roster move.
  2. A correlation across every team-offseason pair, not just the extremes.
     Cherry-picking the biggest movers and eyeballing them is exactly the
     kind of single-anecdote evidence this project's own gate discipline
     exists to catch.

This does NOT touch Elo or main.py. It's the measurement this whole module
has been missing: is net gameScore change actually informative, or does it
just look informative on the cases that happen to confirm the story?

Usage:
    python roster_change_vs_record.py
    python roster_change_vs_record.py --min-games-played 20
"""

import argparse
from pathlib import Path

import requests

from roster_turnover import NHL_TEAMS, build_league_boxscore_rosters, net_gamescore_change

TRANSITIONS = [
    ("20232024", "20242025", "2024-04-15", "2025-04-15"),
    ("20242025", "20252026", "2025-04-15", "2026-04-15"),
]


def get_standings(date: str) -> dict:
    """{team_abbrev: {"points": int, "games_played": int, "point_pct": float}}
    from the standings snapshot closest to end-of-regular-season on `date`."""
    r = requests.get(f"https://api-web.nhle.com/v1/standings/{date}", timeout=20)
    r.raise_for_status()
    out = {}
    for row in r.json().get("standings", []):
        abbrev = row["teamAbbrev"]["default"]
        out[abbrev] = {
            "points": row["points"],
            "games_played": row["gamesPlayed"],
            "point_pct": row["pointPctg"],
        }
    return out


def build_dataset(min_games_played: int = 15, verbose: bool = True) -> list:
    rows = []
    for from_season, to_season, from_date, to_date in TRANSITIONS:
        if verbose:
            print(f"\n=== {from_season} -> {to_season} ===")
        league_rosters = build_league_boxscore_rosters(from_season, verbose=verbose)
        from_standings = get_standings(from_date)
        to_standings = get_standings(to_date)

        for team in NHL_TEAMS:
            r = net_gamescore_change(team, from_season, to_season,
                                     min_games_played=min_games_played,
                                     league_rosters=league_rosters)
            if r["n_kept"] + r["n_departed"] + r["n_arrived"] == 0:
                continue  # team didn't exist in from_season

            from_rec = from_standings.get(team)
            to_rec = to_standings.get(team)
            if not from_rec or not to_rec:
                continue  # team didn't exist / relocated between snapshots

            rows.append({
                "team": team,
                "from_season": from_season,
                "to_season": to_season,
                "net_gameScore_change": r["net_gameScore_change"],
                "n_departed": r["n_departed"],
                "n_arrived": r["n_arrived"],
                "from_point_pct": from_rec["point_pct"],
                "to_point_pct": to_rec["point_pct"],
                "point_pct_change": to_rec["point_pct"] - from_rec["point_pct"],
                "from_points": from_rec["points"],
                "to_points": to_rec["points"],
            })
    return rows


def correlation(xs: list, ys: list) -> float:
    n = len(xs)
    if n < 3:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    if sx == 0 or sy == 0:
        return float("nan")
    return cov / (sx * sy)


def print_report(rows: list) -> None:
    ranked = sorted(rows, key=lambda r: -r["net_gameScore_change"])

    print("\n" + "=" * 92)
    print("  BIGGEST BUYERS — largest positive net gameScore swing")
    print("=" * 92)
    print(f"{'Team':<6}{'Offseason':<20}{'Net Δ':>9}{'Point% before':>15}"
          f"{'Point% after':>14}{'Change':>9}")
    print("-" * 92)
    for r in ranked[:8]:
        chg = r["point_pct_change"]
        print(f"{r['team']:<6}{r['from_season'][:4]}-{r['to_season'][2:4]:<15}"
              f"{r['net_gameScore_change']:>+9.1f}{r['from_point_pct']:>15.3f}"
              f"{r['to_point_pct']:>14.3f}{chg:>+9.3f}")

    print("\n" + "=" * 92)
    print("  BIGGEST SELLERS — largest negative net gameScore swing")
    print("=" * 92)
    print(f"{'Team':<6}{'Offseason':<20}{'Net Δ':>9}{'Point% before':>15}"
          f"{'Point% after':>14}{'Change':>9}")
    print("-" * 92)
    for r in ranked[-8:][::-1]:
        chg = r["point_pct_change"]
        print(f"{r['team']:<6}{r['from_season'][:4]}-{r['to_season'][2:4]:<15}"
              f"{r['net_gameScore_change']:>+9.1f}{r['from_point_pct']:>15.3f}"
              f"{r['to_point_pct']:>14.3f}{chg:>+9.3f}")

    xs = [r["net_gameScore_change"] for r in rows]
    ys = [r["point_pct_change"] for r in rows]
    r_val = correlation(xs, ys)

    buyers = [r for r in rows if r["net_gameScore_change"] > 0]
    sellers = [r for r in rows if r["net_gameScore_change"] <= 0]
    buyer_improved = sum(1 for r in buyers if r["point_pct_change"] > 0)
    seller_declined = sum(1 for r in sellers if r["point_pct_change"] < 0)

    print("\n" + "=" * 92)
    print(f"  ACROSS ALL {len(rows)} TEAM-OFFSEASONS (not just the extremes)")
    print("=" * 92)
    print(f"  Correlation (net gameScore change vs point% change): {r_val:+.3f}")
    print(f"  Net BUYERS ({len(buyers)}) whose point% actually improved: "
          f"{buyer_improved}/{len(buyers)} ({buyer_improved/len(buyers):.0%})" if buyers else "  No net buyers.")
    print(f"  Net SELLERS ({len(sellers)}) whose point% actually declined: "
          f"{seller_declined}/{len(sellers)} ({seller_declined/len(sellers):.0%})" if sellers else "  No net sellers.")
    print("-" * 92)
    if abs(r_val) < 0.2 or r_val != r_val:
        print("  Weak/no correlation. Net gameScore change does not look like a")
        print("  reliable predictor of next-season record on this sample.")
    elif r_val > 0:
        print("  Positive correlation — teams that gained more gameScore tended to")
        print("  improve more. Worth a bigger sample before trusting further.")
    else:
        print("  Negative correlation — the OPPOSITE of what the signal should show.")
        print("  Worth investigating before using this for anything.")
    print(f"  n={len(rows)} is small — 2 offseasons x ~32 teams. Treat this as a")
    print("  first look, not a conclusion.")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--min-games-played", type=int, default=15)
    args = parser.parse_args()

    rows = build_dataset(min_games_played=args.min_games_played)
    print_report(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
