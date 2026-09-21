"""
Append-only pre-game prediction log (mirrors nhllines/src/analysis/prediction_log.py).

Every predict.py run appends one JSON line per game to
data/predictions_log.jsonl: UTC timestamp, run date, game id, teams, week,
win probability, expected home/away points, margin, total, and the model
version. Lines are never rewritten; a (game_id, run_date) pair is written
once, so re-running on the same day doesn't duplicate. A prediction only
counts if it was logged before kickoff — the scorecard drops the rest.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parents[2] / "data" / "predictions_log.jsonl"
# v2 (2026-09-18): margin and team points derived from the win probability
# (src/models/coherent.py); only the total comes from the points model.
MODEL_VERSION = "nfl-win-v1+coherent-points-v2"


def _existing_keys(path: Path) -> set:
    keys = set()
    if not path.exists():
        return keys
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        keys.add((r.get("game_id"), r.get("run_date")))
    return keys


def log_predictions(rows: list, path: Path = LOG_PATH, model_version: str = MODEL_VERSION) -> int:
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
            rec = {"timestamp_utc": now.isoformat(), "run_date": run_date, "model_version": model_version, **r}
            f.write(json.dumps(rec, default=str) + "\n")
            written += 1
    return written
