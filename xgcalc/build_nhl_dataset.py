#!/usr/bin/env python3
"""Build data/nhl_shots.parquet from the raw NHL feed nhl_backfill.py cached.

One row per shot attempt, blocked shots included (event == "BLOCK"), with the
columns src/data/nhl_events.py documents. Where MoneyPuck's dataset
(data/shots.parquet, 2018+) has the same shot, its xG is joined on as
`mp_xg`: the benchmark, never a feature.

  python build_nhl_dataset.py                    every cached season
  python build_nhl_dataset.py --seasons 2024 2025
"""
import argparse, gzip, json, sys
from multiprocessing import Pool
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from src.data.nhl_events import game_shots  # noqa: E402

CACHE = ROOT / "cache" / "nhl"
OUT = ROOT / "data" / "nhl_shots.parquet"


def _load(p):
    with gzip.open(p, "rt") as f:
        return json.load(f)


def load_bios(season_dir):
    bios = {}
    for kind in ("skater", "goalie"):
        p = season_dir / f"bios_{kind}.json.gz"
        if not p.exists():
            continue
        for r in _load(p).get("data", []):
            bios[r["playerId"]] = {"hand": r.get("shootsCatches"), "birth": r.get("birthDate"),
                                   "height": r.get("height")}
    return bios


def _one(args):
    pbp_path, bios = args
    sh_path = Path(str(pbp_path).replace(".pbp.", ".shifts."))
    pbp = _load(pbp_path)
    shifts = _load(sh_path) if sh_path.exists() else None
    return game_shots(pbp, shifts, bios)


def build_season(year, pool):
    d = CACHE / str(year)
    bios = load_bios(d)
    files = sorted(d.glob("*.pbp.json.gz"))
    rows, totals = [], {}
    for r, rep in pool.imap_unordered(_one, [(f, bios) for f in files], chunksize=16):
        rows += r
        for k, v in rep.items():
            totals[k] = totals.get(k, 0) + v
    df = pd.DataFrame(rows)
    print(f"{year}: {len(files)} games, {len(df):,} shots kept  {totals}", flush=True)
    return df


def join_moneypuck(df):
    """Attach MoneyPuck's xG to the unblocked shots it also has."""
    mp_path = ROOT / "data" / "shots.parquet"
    if not mp_path.exists():
        df["mp_xg"] = float("nan")
        return df
    mp = pd.read_parquet(mp_path, columns=["season", "game_id", "period", "time_seconds",
                                           "shooter_id", "event", "mp_xg"])
    mp["game_id"] = mp["season"].astype("int64") * 1_000_000 + mp["game_id"]
    mp = mp.drop(columns="season")
    mp["shooter_id"] = mp["shooter_id"].astype("float64")
    mp = mp.drop_duplicates(["game_id", "period", "time_seconds", "shooter_id", "event"],
                            keep=False)
    keys = ["game_id", "period", "time_seconds", "shooter_id", "event"]
    left = df.assign(shooter_id=df["shooter_id"].astype("float64"))
    out = left.merge(mp, on=keys, how="left")
    out["shooter_id"] = df["shooter_id"].to_numpy()
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seasons", nargs="+", type=int,
                    help="start years (default: every cached season)")
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args()
    years = a.seasons or sorted(int(p.name) for p in CACHE.iterdir()
                                if p.is_dir() and p.name.isdigit())
    with Pool() as pool:
        df = pd.concat([build_season(y, pool) for y in years], ignore_index=True)
    df = df.sort_values(["game_id", "sort_order"]).reset_index(drop=True)
    df = join_moneypuck(df)
    unblocked = df[df.event != "BLOCK"]
    matched = unblocked.mp_xg.notna()
    print(f"\n{len(df):,} shots ({len(unblocked):,} unblocked, "
          f"{int(df.goal.sum()):,} goals). MoneyPuck xG matched on "
          f"{matched.sum():,} unblocked shots "
          f"({matched[unblocked.season >= 2018].mean():.1%} of 2018+).")
    for c in ("shoot_on_ice", "def_on_ice"):
        df[c] = df[c].astype("string")
    a.out.parent.mkdir(exist_ok=True)
    df.to_parquet(a.out, index=False)
    print(f"Wrote {a.out} ({a.out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
