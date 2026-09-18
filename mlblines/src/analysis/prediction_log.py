"""
Append-only MLB prediction log (mlbdata/predictions_log.jsonl).
===============================================================
A prediction only counts if it was written down before first pitch. Every
daily run appends one line per game that hasn't started: UTC timestamp, game
id, teams, starters, calibrated home win probability, expected total, the
market's devigged price at that moment, and the model versions that produced
the numbers. Existing lines are never rewritten; a game is logged at most once
per run date.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parents[2] / "mlbdata" / "predictions_log.jsonl"


def _existing_keys(path: Path) -> set:
    keys = set()
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            keys.add((row.get("game_id"), row.get("run_date")))
    return keys


def log_predictions(rows: list, path: Path = LOG_PATH) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _existing_keys(path)
    now = datetime.now(timezone.utc)
    run_date = now.strftime("%Y-%m-%d")
    written = 0
    with open(path, "a") as f:
        for r in rows:
            key = (r["game_id"], run_date)
            if key in existing:
                continue
            existing.add(key)
            f.write(json.dumps({"timestamp_utc": now.isoformat(), "run_date": run_date, **r},
                               default=str) + "\n")
            written += 1
    return written
