#!/usr/bin/env python3
"""
Market-benchmark snapshot job.
==============================
Ported from nhllines/scripts/snapshot_market.py — same rationale: the
betting market's closing consensus is the strongest public predictor of an
MLB game, and scoring the model against it honestly requires the market's
implied probabilities to be captured and archived *before* each game, not
reconstructed after the fact.

This script fetches current consensus odds via the existing odds fetcher,
devigs them to implied probabilities (src.data.odds_fetcher.get_consensus_no_vig_odds),
and writes one dated JSON file per run to mlbdata/market_snapshots/.

Cron-friendly: no interactive input, clear stdout summary, and an explicit
exit-code contract for the scheduled job — 0 on success (an empty board
included, since off-season and dark days are normal), 2 when every API key
was rejected (a credentials problem only a human can fix), 1 for anything
else. An empty board costs no API credits: /events is billed at 0.

Usage:
    python scripts/snapshot_market.py
    python scripts/snapshot_market.py --skip-empty   # what the scheduled job runs

Schedule: `.github/workflows/mlb-market-snapshot.yml` runs this 3x daily and
commits each snapshot — 2 during the day plus one near typical first pitch
(most MLB games start 19:00-19:15 US/Eastern). A snapshot not taken before a
game cannot be reconstructed after it.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.data.odds_fetcher import (
    AllKeysRejected,
    fetch_mlb_odds,
    fetch_upcoming_events,
    get_consensus_no_vig_odds,
    get_quota_summary,
    parse_odds,
)

SNAPSHOT_DIR = Path(__file__).resolve().parents[1] / "mlbdata" / "market_snapshots"


def take_snapshot(skip_empty: bool = False) -> tuple:
    """Fetch, devig, and write one snapshot. Returns (out_path, snapshot_dict).

    With `skip_empty`, an empty board writes nothing and returns (None,
    snapshot) — the scheduled job runs year-round, and off-season/no-game-day
    zero-game snapshots are noise in a record whose whole value is the games
    it actually captured."""
    # Free preflight: the Odds API bills /events at 0 credits, so an empty
    # board — the MLB off-season, or simply a dark day — is discovered
    # without spending a request, and a rejected key is reported as a
    # credentials problem rather than as a 401 midway through the paid call.
    if fetch_upcoming_events("baseball_mlb"):
        raw_games, quota = fetch_mlb_odds()
        games = parse_odds(raw_games)
    else:
        games, quota = [], get_quota_summary()

    now = datetime.now(timezone.utc)
    snapshot = {
        "timestamp_utc": now.isoformat(),
        "sport": "baseball_mlb",
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
    parser.add_argument("--skip-empty", action="store_true",
                        help="Write no file when the board is empty (used by the "
                             "scheduled workflow, which runs year-round).")
    args = parser.parse_args()

    try:
        out_path, snapshot = take_snapshot(skip_empty=args.skip_empty)
    except AllKeysRejected as e:
        # Exit 2, not 1: the scheduled workflow reports a dead/exhausted key as
        # the credentials problem it is, since only a human can rotate them.
        print(f"Odds API credentials rejected: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"Market snapshot failed: {e}", file=sys.stderr)
        return 1

    if snapshot["n_games"] == 0:
        wrote = f"wrote an empty snapshot to {out_path}" if out_path else "wrote nothing"
        print(f"No games currently on the MLB odds board — {wrote}.")
    else:
        print(f"Wrote {snapshot['n_games']} game(s) to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
