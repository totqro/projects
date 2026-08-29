#!/usr/bin/env python3
"""
Sanity-check the built shot dataset before anyone trains on it.

    python validate_dataset.py

Checks that the cleaned data behaves like hockey (goal rate falls with
distance and angle), that nothing was lost or duplicated (MoneyPuck's xG
should sum to roughly the actual goal count), and that no feature column
carries nulls. Exits non-zero if a hard check fails.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from src.data.schema import FEATURE_COLUMNS, LEAKY_COLUMNS

DATA_DIR = Path(__file__).resolve().parent / "data"

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}{'  ' + detail if detail else ''}")
    if not ok:
        failures.append(name)


def load() -> pd.DataFrame:
    for candidate in ("shots.parquet", "shots.csv.gz"):
        path = DATA_DIR / candidate
        if path.exists():
            return pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
    raise FileNotFoundError(f"No dataset in {DATA_DIR}. Run build_dataset.py first.")


def main() -> int:
    df = load()
    no_en = df[df.is_empty_net == 0]
    print(f"Loaded {len(df):,} shots, seasons {df.season.min()}-{df.season.max()}\n")

    print("Integrity")
    check("no null features", df[FEATURE_COLUMNS].isna().sum().sum() == 0)
    check("no duplicate shot keys",
          df.duplicated(["season", "game_id", "shot_id"]).sum() == 0)
    check("label is binary", set(df.goal.unique()) <= {0, 1})
    check("adjusted x is one-sided", (df.x_adj >= 0).all(),
          "(every shot attacks the net at x=+89)")
    check("no leaky column in features",
          not set(FEATURE_COLUMNS) & set(LEAKY_COLUMNS))

    print("\nCalibration against MoneyPuck")
    ratio = df.mp_xg.sum() / df.goal.sum()
    check("mp_xg sums to actual goals", 0.97 <= ratio <= 1.03,
          f"(ratio {ratio:.4f} — off means rows were lost or duplicated)")

    print("\nHockey sanity (goalie in net)")
    dist_buckets = pd.cut(no_en.distance, [0, 10, 20, 30, 40, 50, 60, 100])
    by_dist = no_en.groupby(dist_buckets, observed=True).goal.mean()
    check("goal rate falls monotonically with distance",
          bool((by_dist.diff().dropna() < 0).all()),
          f"({by_dist.iloc[0]:.3f} close-in -> {by_dist.iloc[-1]:.3f} far)")

    angle_buckets = pd.cut(no_en.angle_from_net, [0, 30, 60, 90])
    by_angle = no_en.groupby(angle_buckets, observed=True).goal.mean()
    check("goal rate falls as the angle sharpens",
          bool((by_angle.diff().dropna() < 0).all()),
          f"({by_angle.iloc[0]:.3f} -> {by_angle.iloc[-1]:.3f})")

    check("rebounds score more often than non-rebounds",
          no_en[no_en.is_rebound == 1].goal.mean() > no_en[no_en.is_rebound == 0].goal.mean(),
          f"({no_en[no_en.is_rebound == 1].goal.mean():.3f} vs "
          f"{no_en[no_en.is_rebound == 0].goal.mean():.3f})")

    check("empty-net shots score far more often",
          df[df.is_empty_net == 1].goal.mean() > 0.4,
          f"({df[df.is_empty_net == 1].goal.mean():.3f})")

    check("power play beats even strength",
          df[df.strength_bucket == "PP"].goal.mean() > df[df.strength_bucket == "EV"].goal.mean(),
          f"(PP {df[df.strength_bucket == 'PP'].goal.mean():.3f} vs "
          f"EV {df[df.strength_bucket == 'EV'].goal.mean():.3f})")

    # Guards the OT-format split: regular-season OT is 3v3 and scores at
    # roughly twice the regulation rate, playoff OT is 5v5 and scores below
    # it. If these ever converge, period_format has stopped distinguishing
    # them and every period-4 shot is being modelled as one environment.
    ev = df[df.strength_bucket == "EV"]
    r3 = ev[ev.period_format == "OT_3v3"].goal.mean()
    p5 = ev[ev.period_format == "OT_5v5"].goal.mean()
    reg = ev[ev.period_format == "REGULATION"].goal.mean()
    check("3v3 OT scores well above regulation", r3 > reg * 1.5,
          f"(3v3 {r3:.3f} vs regulation {reg:.3f})")
    check("playoff 5v5 OT scores at or below regulation", p5 < reg,
          f"(playoff OT {p5:.3f} vs regulation {reg:.3f})")
    check("no shootout attempts present",
          int(((df.is_playoff == 0) & (df.period >= 5)).sum()) == 0,
          "(regular-season period 5+ would be the shootout)")
    check("regular-season OT is 3v3-based",
          df[(df.is_playoff == 0) & (df.period == 4)].strength_state.mode()[0] == "3v3")
    check("playoff OT is 5v5-based",
          df[(df.is_playoff == 1) & (df.period >= 4)].strength_state.mode()[0] == "5v5")

    # Guards the pulled-goalie fix: bucketing on raw skater counts put 5v6
    # empty-net shots in "SH" and pushed its goal rate above .20.
    sh_rate = df[df.strength_bucket == "SH"].goal.mean()
    check("shorthanded rate is not empty-net contaminated", sh_rate < 0.12,
          f"(SH {sh_rate:.3f}; >.12 means pulled goalies leaked into the bucket)")

    print(f"\n{'=' * 60}")
    if failures:
        print(f"{len(failures)} CHECK(S) FAILED: {', '.join(failures)}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
