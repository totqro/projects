"""
Append-only prediction log (Aug-Sep 2026 milestone, part 2).
=============================================================
"Predictions count only if logged first" (README, philosophy #5) needs a
durable, timestamped record. Every `main.py` run appends one JSON line per
game to `data/predictions_log.jsonl`: UTC timestamp, game id/date/teams, the
calibrated win probability, expected total, and the model version that
produced them.

The file is append-only — existing lines are never rewritten or deleted —
but a given (date, home, away, run_date) tuple is only written once, so
running main.py more than once on the same day doesn't pile up duplicate
rows for a game that hasn't been played yet. Dedup is keyed on teams+date
rather than game_id because the two run paths use different id namespaces
(the odds path logs Odds API hex ids, the no-odds path logs NHL numeric
ids) — teams meet at most once per date, so the tuple is unique either way.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parents[2] / "data" / "predictions_log.jsonl"

# Bump this whenever the win or totals model changes in a way that would
# make old log rows non-comparable to new ones.
MODEL_VERSION = "elo-platt-v1+similarity-totals-v1"


def _existing_keys(path: Path) -> set:
    keys = set()
    if not path.exists():
        return keys
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            keys.add((row.get("date"), row.get("home_team"),
                      row.get("away_team"), row.get("run_date")))
    return keys


def log_predictions(games: list, path: Path = LOG_PATH) -> int:
    """
    Append one JSON line per game to the prediction log.

    Each entry in `games` must be a dict with: game_id, date, home_team,
    away_team, home_win_prob, expected_total. Skips any (date, home, away,
    run_date) tuple already present in the file. Returns the number of new
    lines written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _existing_keys(path)
    now = datetime.now(timezone.utc)
    run_date = now.strftime("%Y-%m-%d")

    written = 0
    with open(path, "a") as f:
        for g in games:
            key = (g.get("date"), g["home_team"], g["away_team"], run_date)
            if key in existing:
                continue
            existing.add(key)
            record = {
                "timestamp_utc": now.isoformat(),
                "run_date": run_date,
                "game_id": g["game_id"],
                "date": g.get("date"),
                "home_team": g["home_team"],
                "away_team": g["away_team"],
                "home_win_prob": g["home_win_prob"],
                "expected_total": g["expected_total"],
                "model_version": MODEL_VERSION,
            }
            f.write(json.dumps(record, default=str) + "\n")
            written += 1
    return written
