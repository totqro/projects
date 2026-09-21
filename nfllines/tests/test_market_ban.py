"""Hard rule 1: no market data in features, ever.

Three checks:
1. No feature column is (or is named after) a market column.
2. No source file under src/features or src/models references a market
   column name.
3. Perturbation: rebuild the features for two seasons with every market
   column replaced by random noise; every feature must be bit-identical.
   A feature derived from any market column would change.
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.data import nflverse as nv
from src.features.build import build_features, feature_columns, load_inputs

ROOT = Path(__file__).resolve().parents[1]
MARKET_TOKENS = ("spread_line", "total_line", "moneyline", "spread_odds", "under_odds", "over_odds")


def test_feature_columns_exclude_market():
    path = nv.PROCESSED_DIR / "features.parquet"
    if not path.exists():
        pytest.skip("run build_dataset.py first")
    cols = feature_columns(pd.read_parquet(path))
    assert not set(cols) & set(nv.MARKET_COLUMNS)
    for c in cols:
        assert not any(tok in c for tok in MARKET_TOKENS), c


def test_feature_code_never_names_market_columns():
    for sub in ("src/features", "src/models", "src/data/team_games.py", "src/data/injury_context.py"):
        for f in (ROOT / sub).rglob("*.py") if (ROOT / sub).is_dir() else [ROOT / sub]:
            text = f.read_text()
            for tok in MARKET_TOKENS:
                assert not re.search(rf"\b{tok}\b", text), f"{f} mentions {tok}"


def test_features_invariant_to_market_columns():
    seasons = (2014, 2015)
    inputs = load_inputs(seasons)
    clean, _ = build_features(inputs=inputs)
    # poison: rebuild inputs from a schedule whose market columns are noise
    rng = np.random.default_rng(1)
    raw = nv.load_games(seasons)
    for c in nv.MARKET_COLUMNS:
        if c in raw.columns:
            raw[c] = rng.normal(size=len(raw)) * 100
    # feature_frame() must drop them; if anything downstream used them, the rows would differ
    from src.data.team_games import normalize_games
    poisoned = dict(inputs)
    poisoned["games"] = normalize_games(nv.feature_frame(raw))
    dirty, _ = build_features(inputs=poisoned)
    cols = feature_columns(clean)
    assert list(clean.game_id) == list(dirty.game_id)
    for c in cols:
        a, b = clean[c].to_numpy(), dirty[c].to_numpy()
        if a.dtype.kind in "OU":
            assert (a == b).all(), c
        else:
            assert np.array_equal(a, b, equal_nan=True), c
