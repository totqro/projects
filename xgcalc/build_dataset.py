#!/usr/bin/env python3
"""
Build the cleaned xG shot dataset from MoneyPuck season files.

    python build_dataset.py                      # all seasons 2018-2025
    python build_dataset.py --seasons 2023 2024 2025
    python build_dataset.py --download           # fetch any missing seasons
    python build_dataset.py --exclude-empty-net  # drop empty-net shots

Writes data/shots.parquet (or data/shots.csv.gz without pyarrow) and prints a
per-season accounting of every row dropped and why.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.data.clean import clean_shots
from src.data.schema import (
    CATEGORICAL_FEATURES,
    FEATURE_COLUMNS,
    LABEL_COLUMN,
)
from src.data.shots import download_season, load_season_raw

DEFAULT_SEASONS = list(range(2018, 2026))
OUT_DIR = Path(__file__).resolve().parent / "data"


def build(seasons, raw_dir=None, download=False, exclude_empty_net=False):
    frames, reports = [], []
    for year in seasons:
        if download:
            download_season(year, raw_dir)
        print(f"  reading {year} ...", end=" ", flush=True)
        raw = load_season_raw(year, raw_dir)
        cleaned, report = clean_shots(raw)
        report["season"] = year
        print(f"{report['rows_in']:,} raw -> {report['rows_out']:,} clean")
        frames.append(cleaned)
        reports.append(report)

    df = pd.concat(frames, ignore_index=True)

    if exclude_empty_net:
        n_en = int(df["is_empty_net"].sum())
        df = df[df["is_empty_net"] == 0].reset_index(drop=True)
        print(f"\n  excluded {n_en:,} empty-net shots (--exclude-empty-net)")

    return df, pd.DataFrame(reports)


def write(df: pd.DataFrame, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        import pyarrow  # noqa: F401

        path = out_dir / "shots.parquet"
        df.to_parquet(path, index=False)
    except ImportError:
        # Parquet is preferred (typed, ~5x smaller); gzipped CSV keeps the
        # builder usable without pyarrow installed.
        path = out_dir / "shots.csv.gz"
        df.to_csv(path, index=False, compression="gzip")
        print("  (pyarrow not installed — wrote gzipped CSV instead of parquet)")
    return path


def summarize(df: pd.DataFrame, reports: pd.DataFrame) -> None:
    print("\n" + "=" * 68)
    print("DROP ACCOUNTING")
    print("=" * 68)
    cols = [c for c in reports.columns if c.startswith("dropped")]
    print(reports.set_index("season")[["rows_in", "rows_out"] + cols].to_string())

    print("\n" + "=" * 68)
    print(f"DATASET: {len(df):,} shots, {len(df.columns)} columns")
    print("=" * 68)
    print(f"  seasons          {df.season.min()}-{df.season.max()}")
    print(f"  goals            {int(df[LABEL_COLUMN].sum()):,} "
          f"({df[LABEL_COLUMN].mean():.4f} base rate)")
    n_en = int(df.is_empty_net.sum())
    en_rate = (f"goal rate {df[df.is_empty_net == 1][LABEL_COLUMN].mean():.3f}"
               if n_en else "excluded")
    print(f"  empty-net shots  {n_en:,} ({en_rate})")
    print(f"  behind-net shots {int(df.is_behind_net.sum()):,}")
    print(f"  rebounds         {int(df.is_rebound.sum()):,} "
          f"(goal rate {df[df.is_rebound == 1][LABEL_COLUMN].mean():.3f})")
    print(f"  features         {len(FEATURE_COLUMNS)} "
          f"({len(CATEGORICAL_FEATURES)} categorical)")

    nulls = df[FEATURE_COLUMNS].isna().sum()
    nulls = nulls[nulls > 0]
    print(f"\n  nulls in feature columns: "
          f"{'none' if nulls.empty else chr(10) + nulls.to_string()}")

    print("\n  goal rate by strength bucket:")
    for bucket, g in df.groupby("strength_bucket", observed=True):
        print(f"    {bucket:<4} {len(g):>8,} shots   {g[LABEL_COLUMN].mean():.4f}")

    print("\n  goal rate by shot type:")
    for st, g in df.groupby("shot_type", observed=True)[
        [LABEL_COLUMN]
    ].agg(["size", "mean"]).droplevel(0, axis=1).sort_values("mean", ascending=False).iterrows():
        print(f"    {st:<8} {int(g['size']):>8,} shots   {g['mean']:.4f}")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--seasons", type=int, nargs="+", default=DEFAULT_SEASONS)
    p.add_argument("--raw-dir", type=Path, default=None,
                   help="directory holding moneypuck_shots_{year}.csv")
    p.add_argument("--download", action="store_true",
                   help="download any season not already cached")
    p.add_argument("--exclude-empty-net", action="store_true",
                   help="drop empty-net shots (recommended for goalie-facing xG)")
    p.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = p.parse_args()

    print(f"Building xG shot dataset for seasons {args.seasons}\n")
    df, reports = build(args.seasons, args.raw_dir, args.download,
                        args.exclude_empty_net)
    summarize(df, reports)
    path = write(df, args.out_dir)
    size_mb = path.stat().st_size / 1e6
    print(f"\nWrote {path} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
