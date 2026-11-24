"""Offline checks for nhl_backfill.fetch_bios (no network). Run: .venv/bin/python tests/test_fetch_bios.py

The stats API caps bios at 100 rows per call (Nov 2026), so fetch_bios pages through them. These tests
stand in a fake API for nhl_backfill.get and check paging, ordering and the short-read guard.
"""
import gzip, json, re, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import nhl_backfill as nb  # noqa: E402


def fake_api(rows, cap=100, drop_page=None):
    """A stand-in for nb.get serving `rows` in pages of at most `cap`, like the real endpoint."""
    def get(url, tries=4):
        limit = int(re.search(r"limit=(-?\d+)", url).group(1))
        start = int(re.search(r"start=(\d+)", url).group(1))
        n = cap if limit < 0 else min(limit, cap)
        page = rows[start:start + n]
        if drop_page is not None and start == drop_page:
            page = page[:-1]                      # the API loses a row on this page
        return {"data": [dict(r) for r in page], "total": len(rows)}
    return get


def rows_for(n_players, playoff_every=0):
    out = []
    for i in range(n_players):
        out.append({"playerId": 8470000 + i, "shootsCatches": "LR"[i % 2], "birthDate": "2000-01-01", "gameTypeId": 2})
        if playoff_every and i % playoff_every == 0:
            out.append({"playerId": 8470000 + i, "shootsCatches": "LR"[i % 2], "birthDate": "2000-01-01", "gameTypeId": 3})
    return out


def with_api(get, fn):
    real = nb.get
    nb.get = get
    try:
        return fn()
    finally:
        nb.get = real


def test_pages_past_the_cap():
    rows = rows_for(789)
    got = with_api(fake_api(rows[::-1]), lambda: nb.fetch_bios("skater", 2026))     # served in reverse order
    ids = [r["playerId"] for r in got["data"]]
    assert len(ids) == 789 and len(set(ids)) == 789 and got["total"] == 789
    assert ids == sorted(ids), "file must be sorted so an unchanged set gives an unchanged file"


def test_duplicate_rows_per_player_are_kept():
    rows = rows_for(300, playoff_every=4)                                          # regular + playoff rows
    got = with_api(fake_api(rows), lambda: nb.fetch_bios("skater", 2024))
    assert len(got["data"]) == len(rows) and got["total"] == len(rows)


def test_same_data_gives_same_bytes():
    rows = rows_for(250, playoff_every=5)
    a = with_api(fake_api(rows), lambda: nb.fetch_bios("skater", 2026))
    b = with_api(fake_api(rows[::-1]), lambda: nb.fetch_bios("skater", 2026))
    assert json.dumps(a) == json.dumps(b)


def test_short_read_raises_and_keeps_the_old_file():
    rows = rows_for(250)
    try:
        with_api(fake_api(rows, drop_page=100), lambda: nb.fetch_bios("skater", 2026))
    except RuntimeError as e:
        assert "249 rows of 250" in str(e), e
    else:
        raise AssertionError("a short read must raise")
    # backfill_season keeps the cached file when the refresh fails
    with tempfile.TemporaryDirectory() as tmp:
        real_cache, real_final = nb.CACHE, nb.final_games
        nb.CACHE, nb.final_games = Path(tmp), (lambda year: [])
        try:
            d = Path(tmp) / "2026"
            d.mkdir()
            old = {"data": [{"playerId": 1}], "total": 1}
            for kind in ("skater", "goalie"):
                nb.save(d / f"bios_{kind}.json.gz", old)
            with_api(fake_api(rows, drop_page=100), lambda: nb.backfill_season(2026, workers=1, refresh_bios=True))
            assert json.load(gzip.open(d / "bios_skater.json.gz", "rt")) == old
        finally:
            nb.CACHE, nb.final_games = real_cache, real_final


def main():
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]
    for n, f in tests:
        f()
        print("ok", n)
    print(f"all {len(tests)} fetch_bios tests passed")


if __name__ == "__main__":
    main()
