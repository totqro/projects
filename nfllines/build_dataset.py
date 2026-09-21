"""
Build the point-in-time feature table for every game (2014 warm-start, 2015-
2023 training, 2024-2025 test) and verify it.

    python build_dataset.py                 # -> data/processed/features.parquet
    python build_dataset.py --verify 40     # + recompute 40 random games from scratch

The verification rebuilds a fresh engine per sampled game, walks only the
weeks strictly before it, calls the SAME features_for() the live path uses,
and asserts every feature matches the stored row exactly (np.isclose with
zero tolerance on finite values). Market columns never enter: the engine is
fed nflverse.feature_frame(), which drops them, and the table written here
keeps them in a separate file (data/processed/market.parquet) for
evaluate_test.py only.
"""
import argparse
import sys
import time

import numpy as np
import pandas as pd

from src.data import nflverse as nv
from src.features.build import build_features, serve_features, feature_columns, load_inputs

OUT = nv.PROCESSED_DIR / "features.parquet"
MARKET_OUT = nv.PROCESSED_DIR / "market.parquet"


def verify(df: pd.DataFrame, inputs: dict, n: int, seed: int = 0) -> bool:
    rng = np.random.default_rng(seed)
    cols = feature_columns(df)
    candidates = df[df.season >= 2015].game_id.to_numpy()
    sample = rng.choice(candidates, size=min(n, len(candidates)), replace=False)
    ok = True
    t = time.time()
    for gid in sample:
        stored = df[df.game_id == gid].iloc[0]
        fresh = serve_features(inputs, gid)
        bad = []
        for c in cols:
            a, b = stored[c], fresh.get(c)
            if isinstance(a, str) or isinstance(b, str):
                if a != b:
                    bad.append((c, a, b))
            elif not (np.isclose(float(a), float(b), rtol=0, atol=0) or (np.isnan(float(a)) and np.isnan(float(b)))):
                bad.append((c, a, b))
        if bad:
            ok = False
            print(f"  MISMATCH {gid}: " + ", ".join(f"{c}: stored={a} fresh={b}" for c, a, b in bad[:5]))
    print(f"verified {len(sample)} games x {len(cols)} features in {time.time()-t:.0f}s: "
          + ("ALL EXACT" if ok else "FAILED"))
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verify", type=int, default=0, help="recompute N random games from scratch")
    args = ap.parse_args()

    t = time.time()
    inputs = load_inputs(nv.ALL_SEASONS)
    df, _ = build_features(inputs=inputs)
    nv.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)
    inputs["market"].to_parquet(MARKET_OUT, index=False)
    cols = feature_columns(df)
    assert not set(cols) & set(nv.MARKET_COLUMNS), "market column leaked into features"
    print(f"wrote {OUT}: {len(df)} games, {len(cols)} feature columns  [{time.time()-t:.0f}s]")
    print(df.groupby("season").size().to_dict())
    if args.verify:
        if not verify(df, inputs, args.verify):
            sys.exit(1)


if __name__ == "__main__":
    main()
