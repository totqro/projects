"""
Calibration: Platt vs isotonic vs raw, chosen by LOSO inside 2015-2023.
=======================================================================
The win model's out-of-fold probabilities (data/processed/win_oof.parquet,
written by model_gate.py) are already honest: each season's p was produced
by a model that never saw that season. The calibrator is then itself fit
LOSO on those OOF probabilities — for held-out season s, fit on the other
eight seasons' OOF (p, y), apply to season s — so the calibrated numbers
scored here are doubly out-of-sample. A method is adopted only if it beats
the raw probabilities on BOTH log loss and Brier; ECE and a reliability
table are reported either way. The adopted calibrator (refit on all nine
seasons) is written into ml_models/win_model.json.

    python calibrate.py
"""
import json

import numpy as np
import pandas as pd

from src.data import nflverse as nv
from src.models.calibration import fit_calibrator
from src.models.loso import folds, beats
from src.models.metrics import win_metrics, reliability_table
from src.models.win_model import WIN_MODEL_PATH


def loso_calibrated(df: pd.DataFrame, method: str) -> np.ndarray:
    out = np.full(len(df), np.nan)
    for s, tr, te in folds(df):
        cal = fit_calibrator(method, df.p_oof[tr].to_numpy(), df.home_win[tr].to_numpy())
        out[te.to_numpy()] = cal.predict(df.p_oof[te].to_numpy())
    return out


def main():
    df = pd.read_parquet(nv.PROCESSED_DIR / "win_oof.parquet")
    df = df[df.season.isin(nv.TRAIN_SEASONS)].reset_index(drop=True)
    y = df.home_win.to_numpy(int)
    results = {}
    probs = {"uncalibrated": df.p_oof.to_numpy()}
    for m in ("platt", "isotonic"):
        probs[m] = loso_calibrated(df, m)
    print("=" * 78); print("  CALIBRATION — LOSO 2015-2023 on the win model's out-of-fold probabilities"); print("=" * 78)
    print(f"{'Method':<16}{'Accuracy':>10}{'Log loss':>11}{'Brier':>9}{'ECE':>9}")
    for m, p in probs.items():
        r = win_metrics(y, p); results[m] = r
        print(f"{m:<16}{r['accuracy']:>10.3f}{r['log_loss']:>11.4f}{r['brier']:>9.4f}{r['ece']:>9.4f}")
    base = results["uncalibrated"]; chosen = None
    for m in ("platt", "isotonic"):
        if beats(results[m], base)["passed"] and (chosen is None or beats(results[m], results[chosen])["passed"]):
            chosen = m
    print()
    if chosen is None:
        print("VERDICT: keep RAW probabilities — neither calibrator beats them on both log loss and Brier.")
    else:
        print(f"VERDICT: adopt {chosen} (beats raw on both log loss and Brier).")
    print("\nReliability table (chosen or raw):")
    p = probs[chosen or "uncalibrated"]
    print(f"{'bin':<10}{'n':>6}{'mean_pred':>11}{'frac_pos':>10}")
    for r in reliability_table(y, p):
        if r["n"]:
            print(f"{r['bin']:<10}{r['n']:>6}{r['mean_pred']:>11.3f}{r['frac_pos']:>10.3f}")
    # write into the shipped model
    with open(WIN_MODEL_PATH) as f:
        model = json.load(f)
    if chosen:
        cal = fit_calibrator(chosen, df.p_oof.to_numpy(), y)
        model["calibrator"] = cal.to_dict()
    else:
        model["calibrator"] = None
    model["calibration_report"] = {m: {k: v for k, v in r.items()} for m, r in results.items()}
    model["calibration_chosen"] = chosen
    with open(WIN_MODEL_PATH, "w") as f:
        json.dump(model, f, indent=1)
    print("updated", WIN_MODEL_PATH)


if __name__ == "__main__":
    main()
