#!/usr/bin/env python3
"""
Rebuild the MLB point-in-time training set and refit the shipped models.
========================================================================
1. Fetch every regular-season game since 2021 plus each probable starter's
   game logs (MLB Stats API, cached) and replay them into point-in-time rows:
   mlbdata/training_set.csv.
2. Run the win gate and the totals gate (see model_gate.py).
3. Fit whichever model each gate picked and write the artifacts the daily run
   loads: ml_models/win_model.json and ml_models/totals_model.json. Each file
   carries the gate numbers that justified it.

Usage:
    python build_training_set.py
"""

import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
warnings.filterwarnings("ignore", category=RuntimeWarning)

from src.data.historical_dataset import build_rows, load_history, write_csv
from src.models import totals_model, win_model

BASE = Path(__file__).resolve().parent
TRAINING_SET = BASE / "mlbdata" / "training_set.csv"


def _slim_win_gate(g: dict) -> dict:
    keep = ("always_home", "elo", "pitcher")
    return {
        "test_season": g["primary"]["test_season"],
        "train_seasons": g["primary"]["train_seasons"],
        **{k: g["primary"][k] for k in keep},
        "passed": g["passed"],
        "loso": [{"test_season": r["test_season"], "elo_log_loss": r["elo"]["log_loss"],
                  "pitcher_log_loss": r["pitcher"]["log_loss"],
                  "pitcher_beats_elo": r["pitcher_beats_elo"]} for r in g["loso"]],
    }


def main() -> int:
    print("Fetching MLB history (cached after the first run)...")
    schedules, index = load_history()
    rows, _ = build_rows(schedules, index)
    write_csv(rows, TRAINING_SET)
    print(f"Wrote {len(rows)} point-in-time rows to {TRAINING_SET}")

    win_gate = win_model.run_gate(rows)
    calibration = win_model.run_calibration_check(rows, win_gate["winner"])
    win = win_model.fit_production(rows, win_gate["winner"], calibration.get("adopted", False))
    win["fitted_at"] = datetime.now(timezone.utc).isoformat()
    win["gate"] = _slim_win_gate(win_gate)
    win["calibration_check"] = {k: v for k, v in calibration.items() if k != "platt_params"}
    win_model.save(win)

    totals_gate = totals_model.run_gate(rows)
    totals = totals_model.fit_production(rows, totals_gate["winner"])
    totals["fitted_at"] = win["fitted_at"]
    totals["gate"] = {"test_season": totals_gate["primary"]["test_season"],
                      "baseline": totals_gate["primary"]["baseline"],
                      "glm": totals_gate["primary"]["glm"],
                      "passed": totals_gate["passed"],
                      "loso_glm_wins": totals_gate["loso_glm_wins"],
                      "loso_seasons": len(totals_gate["loso"])}
    totals_model.save(totals)

    p = win_gate["primary"]
    print(f"\nWin gate ({p['test_season']} held out): Elo ll {p['elo']['log_loss']:.4f}, "
          f"pitcher ll {p['pitcher']['log_loss']:.4f} -> shipping '{win['model']}' "
          f"({'Platt' if win['calibrator']['method'] == 'platt' else 'raw probabilities'}), "
          f"LOSO {win_gate['loso_pitcher_wins']}/{len(win_gate['loso'])}")
    print(f"Totals gate: shipping '{totals['model']}', "
          f"LOSO {totals_gate['loso_glm_wins']}/{len(totals_gate['loso'])}")
    print(f"Wrote {win_model.WIN_MODEL_PATH} and {totals_model.TOTALS_MODEL_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
