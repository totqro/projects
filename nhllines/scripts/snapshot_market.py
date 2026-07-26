#!/usr/bin/env python3
"""
Market-benchmark snapshot job (Aug-Sep 2026 milestone, part 3).
================================================================
The betting market's closing consensus is the strongest public predictor of
an NHL game (~59-60% accurate, log loss ~0.66) — see README "The market is
the benchmark". To score the prediction model against it honestly all
season, the market's implied probabilities need to be captured and archived
*before* each game, not reconstructed after the fact.

This script fetches current consensus odds via the existing odds fetcher,
devigs them to implied probabilities (src.data.odds_fetcher.get_consensus_no_vig_odds),
and writes one dated JSON file per run to data/market_snapshots/.

Cron-friendly: no interactive input, clear stdout summary, exit 0 on success
(including an empty slate) and exit 1 only on a genuine fetch failure.

Usage:
    python scripts/snapshot_market.py
    python scripts/snapshot_market.py --sport baseball_mlb   # smoke test in the NHL off-season
    python scripts/snapshot_market.py --skip-empty           # what the scheduled job runs

Schedule: `.github/workflows/market-snapshot.yml` runs this 3x daily and
commits each snapshot — 2 during the day plus one near typical puck drop
(most NHL games start 19:00-19:30 US/Eastern). It must be a scheduled job on
infrastructure that is actually up: a snapshot not taken before a game
cannot be reconstructed after it, and the season scorecard has no benchmark
without it.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.data.odds_fetcher import fetch_nhl_odds, parse_odds, get_consensus_no_vig_odds

SNAPSHOT_DIR = Path(__file__).resolve().parents[1] / "data" / "market_snapshots"


def take_snapshot(sport: str = "icehockey_nhl", skip_empty: bool = False) -> tuple:
    """Fetch, devig, and write one snapshot. Returns (out_path, snapshot_dict).

    With `skip_empty`, an empty board writes nothing and returns (None,
    snapshot) — the scheduled job runs year-round, and months of off-season
    zero-game snapshots are noise in a record whose whole value is the games
    it actually captured."""
    raw_games, quota = fetch_nhl_odds(sport=sport)
    games = parse_odds(raw_games)

    now = datetime.now(timezone.utc)
    snapshot = {
        "timestamp_utc": now.isoformat(),
        "sport": sport,
        "n_games": len(games),
        "quota": quota,
        "games": [],
    }

    for g in games:
        devigged = get_consensus_no_vig_odds(g)
        snapshot["games"].append({
            "game_id": g["game_id"],
            "commence_time": g["commence_time"],
            "home_team": g["home_team"],
            "away_team": g["away_team"],
            "home_win_prob": devigged["home_win_prob"],
            "away_win_prob": devigged["away_win_prob"],
            "over_prob": devigged["over_prob"],
            "under_prob": devigged["under_prob"],
            "total_line": devigged["total_line"],
            "spread_line": devigged["spread_line"],
            "spread_home_cover_prob": devigged["spread_home_cover_prob"],
            "n_books_ml": devigged["n_books_ml"],
        })

    if skip_empty and not games:
        return None, snapshot

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SNAPSHOT_DIR / f"{now.strftime('%Y-%m-%d_%H%M')}.json"
    out_path.write_text(json.dumps(snapshot, indent=2, default=str))
    return out_path, snapshot


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sport", default="icehockey_nhl",
                        help="Odds API sport key (default: icehockey_nhl). Use "
                             "baseball_mlb to smoke-test the pipeline during the "
                             "NHL off-season, when there's nothing on the NHL board.")
    parser.add_argument("--skip-empty", action="store_true",
                        help="Write no file when the board is empty (used by the "
                             "scheduled workflow, which runs year-round).")
    args = parser.parse_args()

    try:
        out_path, snapshot = take_snapshot(args.sport, skip_empty=args.skip_empty)
    except Exception as e:
        print(f"Market snapshot failed: {e}", file=sys.stderr)
        return 1

    if snapshot["n_games"] == 0:
        wrote = f"wrote an empty snapshot to {out_path}" if out_path else "wrote nothing"
        print(f"No games currently on the {args.sport} odds board — {wrote} "
              f"(expected during the NHL off-season).")
    else:
        print(f"Wrote {snapshot['n_games']} game(s) to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
