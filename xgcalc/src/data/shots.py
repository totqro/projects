"""
Locate and read raw MoneyPuck season shot files.
================================================

Seasons 2018-2025 are already cached by the nhllines win predictor
(nhllines/cache/moneypuck_shots_{year}.csv, ~65MB each). We read those in
place by default instead of re-downloading 500MB. Point RAW_DIR elsewhere, or
pass --raw-dir, to use a different location; download_season() fetches and
extracts a season that isn't there yet.
"""

import io
import zipfile
from pathlib import Path

import pandas as pd

from .schema import SOURCE_COLUMNS

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Default to the win predictor's existing cache — same files, already on disk.
RAW_DIR = PROJECT_ROOT.parent / "nhllines" / "cache"

MONEYPUCK_SHOTS_URL = "https://moneypuck.com/moneypuck/playerData/shots/shots_{year}.zip"

# MoneyPuck 302-redirects bare requests to a license page without these.
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; xgcalc-research/1.0)",
    "Referer": "https://moneypuck.com/data.htm",
}


def season_path(year: int, raw_dir: Path | None = None) -> Path:
    return (raw_dir or RAW_DIR) / f"moneypuck_shots_{year}.csv"


def download_season(year: int, raw_dir: Path | None = None) -> Path:
    """Fetch and extract one season's shots zip. Skips if already present."""
    import requests  # imported lazily so the builder works offline

    dest = season_path(year, raw_dir)
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)

    resp = requests.get(MONEYPUCK_SHOTS_URL.format(year=year), headers=_HEADERS, timeout=180)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = [n for n in zf.namelist() if n.endswith(".csv")]
        if not names:
            raise ValueError(f"No CSV inside MoneyPuck shots zip for {year}")
        tmp = dest.with_suffix(".csv.tmp")
        with zf.open(names[0]) as src, open(tmp, "wb") as out:
            out.write(src.read())
        tmp.replace(dest)
    return dest


def load_season_raw(year: int, raw_dir: Path | None = None) -> pd.DataFrame:
    """Read one season's shots, only the columns the schema declares.

    Every column in SOURCE_COLUMNS was verified present in all of 2018-2025,
    so a missing one means the file format changed — raise loudly rather than
    quietly building a dataset with holes in it.
    """
    path = season_path(year, raw_dir)
    if not path.exists():
        raise FileNotFoundError(
            f"No raw shots file at {path}. Run with --download to fetch it "
            f"from MoneyPuck, or pass --raw-dir pointing at your cache."
        )

    header = pd.read_csv(path, nrows=0).columns
    missing = [c for c in SOURCE_COLUMNS if c not in header]
    if missing:
        raise ValueError(
            f"{path.name} is missing expected columns: {missing}. "
            f"MoneyPuck's schema may have changed — update SOURCE_COLUMNS."
        )

    return pd.read_csv(path, usecols=SOURCE_COLUMNS, low_memory=False)
