"""
Locate and read raw MoneyPuck season shot files.
================================================

Seasons 2018-2025 are already cached by the nhllines win predictor
(nhllines/cache/moneypuck_shots_{year}.csv, ~65MB each). We read those in
place by default instead of re-downloading 500MB. Point RAW_DIR elsewhere, or
pass --raw-dir, to use a different location; download_season() fetches and
extracts a season that isn't there yet.
"""

import re
import shutil
import zipfile
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd

from .schema import SOURCE_COLUMNS

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Default to the win predictor's existing cache — same files, already on disk.
RAW_DIR = PROJECT_ROOT.parent / "nhllines" / "cache"

# MoneyPuck has moved its downloads before. Each season is tried at these
# addresses in order, then at whatever shots_*.zip links data.htm lists,
# including multi-season archives like shots_2007-2023.zip.
MONEYPUCK_SHOTS_URL = "https://moneypuck.com/moneypuck/playerData/shots/shots_{year}.zip"
SHOTS_URLS = [
    "https://peter-tanner.com/moneypuck/downloads/shots_{year}.zip",
    MONEYPUCK_SHOTS_URL,
]
DATA_PAGE = "https://moneypuck.com/data.htm"

# MoneyPuck 302-redirects bare requests to a license page without these.
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; xgcalc-research/1.0)",
    "Referer": DATA_PAGE,
}


def season_path(year: int, raw_dir: Path | None = None) -> Path:
    return (raw_dir or RAW_DIR) / f"moneypuck_shots_{year}.csv"


def _fetch_zip(url: str, dest_dir: Path) -> Path | None:
    """Stream a zip to disk. None if it isn't there or isn't a zip."""
    import requests

    resp = requests.get(url, headers=_HEADERS, timeout=600, stream=True)
    if resp.status_code != 200:
        print(f"    {resp.status_code}  {url}")
        return None
    tmp = dest_dir / ("_" + url.rsplit("/", 1)[-1])
    with open(tmp, "wb") as out:
        for chunk in resp.iter_content(1 << 20):
            out.write(chunk)
    if not zipfile.is_zipfile(tmp):
        print(f"    not a zip  {url}")
        tmp.unlink()
        return None
    print(f"    ok  {url} ({tmp.stat().st_size / 1e6:.0f} MB)")
    return tmp


def _listed_archives() -> list[str]:
    import requests

    try:
        html = requests.get(DATA_PAGE, headers=_HEADERS, timeout=60).text
    except requests.RequestException as e:
        print(f"    could not read {DATA_PAGE}: {e}")
        return []
    links = sorted(set(re.findall(r"""href=["']([^"']*shots_[^"']*\.zip)["']""", html)))
    print(f"    {DATA_PAGE} lists: {links or 'no shots_*.zip links'}")
    return [urljoin(DATA_PAGE, h) for h in links]


def _covers(url: str, year: int) -> bool:
    name = url.rsplit("/", 1)[-1]
    m = re.fullmatch(r"shots_(\d{4})(?:-(\d{4}))?\.zip", name)
    if not m:
        return False
    lo, hi = int(m.group(1)), int(m.group(2) or m.group(1))
    return lo <= year <= hi


def _extract(zip_path: Path, years: list[int], raw_dir: Path | None) -> None:
    """Write moneypuck_shots_{year}.csv for each wanted season in the zip."""
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if n.endswith(".csv")]
        if not names:
            raise ValueError(f"No CSV inside {zip_path.name}")
        with zf.open(names[0]) as src:
            if len(years) == 1 and not re.search(r"\d{4}-\d{4}", zip_path.name):
                dest = season_path(years[0], raw_dir)
                tmp = dest.with_suffix(".csv.tmp")
                with open(tmp, "wb") as out:
                    shutil.copyfileobj(src, out, 1 << 20)
                tmp.replace(dest)
                return
            written = set()
            for chunk in pd.read_csv(src, chunksize=200_000, low_memory=False):
                for year, part in chunk[chunk["season"].isin(years)].groupby("season"):
                    dest = season_path(int(year), raw_dir)
                    part.to_csv(dest, mode="a" if year in written else "w",
                                header=year not in written, index=False)
                    written.add(year)


def download_season(year: int, raw_dir: Path | None = None) -> Path:
    """Fetch and extract one season's shots. Skips if already present."""
    dest = season_path(year, raw_dir)
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  downloading {year}")

    tried = []

    def attempt(url: str) -> bool:
        tried.append(url)
        z = _fetch_zip(url, dest.parent)
        if z:
            _save_from(z, url, year, raw_dir)
        return z is not None

    if any(attempt(u.format(year=year)) for u in SHOTS_URLS):
        return dest
    # A single-season file first, then the narrowest archive covering it.
    listed = sorted((u for u in _listed_archives() if _covers(u, year) and u not in tried),
                    key=lambda u: (len(u.rsplit("/", 1)[-1]), u))
    if any(attempt(u) for u in listed):
        return dest
    raise RuntimeError(f"Could not download MoneyPuck shots for {year}; tried {tried}")


def _save_from(zip_path: Path, url: str, year: int, raw_dir: Path | None) -> None:
    """Extract every missing season the file covers, so an archive downloads once."""
    name = url.rsplit("/", 1)[-1]
    m = re.fullmatch(r"shots_(\d{4})-(\d{4})\.zip", name)
    years = [year]
    if m:
        years = [y for y in range(int(m.group(1)), int(m.group(2)) + 1)
                 if y == year or not season_path(y, raw_dir).exists()]
    try:
        _extract(zip_path, years, raw_dir)
    finally:
        zip_path.unlink(missing_ok=True)
    if not season_path(year, raw_dir).exists():
        raise RuntimeError(f"{name} had no rows for season {year}")


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
