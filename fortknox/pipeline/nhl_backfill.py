#!/usr/bin/env python3
"""Download the raw NHL feed for whole seasons into a local cache, once.

For every final regular-season and playoff game it keeps the two public
endpoints nhl_game.py already reads, gzipped and untouched:

  cache/nhl/{season}/{game_id}.pbp.json.gz      play-by-play (shots, coords, events)
  cache/nhl/{season}/{game_id}.shifts.json.gz   shift chart (who was on the ice)

plus per-season player bios (handedness, position, birth date, height):

  cache/nhl/{season}/bios_skater.json.gz, bios_goalie.json.gz

A final game never changes, so a file that exists is never fetched again: the
script resumes where it stopped and the nightly job runs it to pick up new
games. A game whose shift chart came back empty (it lags live games, and a few
old games never got one) is retried on the next run.

  python3 nhl_backfill.py --seasons 2015-2025       2015-16 through 2025-26
  python3 nhl_backfill.py --seasons 2026            the season in progress

Seasons are named by the year they start, as MoneyPuck and schema.py do.
Stdlib only, so CI can run it on a bare python.
"""
import argparse, gzip, html, json, re, sys, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "cache" / "nhl"

GAMES = "https://api.nhle.com/stats/rest/en/game?cayenneExp=season={}"
PBP = "https://api-web.nhle.com/v1/gamecenter/{}/play-by-play"
SHIFTS = "https://api.nhle.com/stats/rest/en/shiftcharts?cayenneExp=gameId={}"
BIOS = ("https://api.nhle.com/stats/rest/en/{}/bios?isAggregate=false&isGame=false"
        "&limit=-1&start=0&cayenneExp=seasonId={}%20and%20gameTypeId%3E=2")

# The HTML time-on-ice reports (TH home, TV visitor): the fallback when the
# shift-chart API has nothing for a game, which happens for whole stretches.
TOI_HTML = "https://www.nhl.com/scores/htmlreports/{}/{}{}.HTM"

GAME_TYPES = {2: "regular", 3: "playoff"}
FINAL = 7  # gameStateId once a game is official
OVER = 6   # gameStateId once it's over, before it's official


def get_text(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "xgcalc-backfill/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("latin-1")
        except urllib.error.HTTPError as e:
            if e.code == 404 or i == tries - 1:
                return None
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if i == tries - 1:
                return None
        time.sleep(2 ** i)


_CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)


def shifts_from_html(gid, pbp):
    """Rebuild shift-chart rows from the HTML reports, matched to player ids
    by team and sweater number. Same shape as the API's typeCode-517 rows."""
    season = f"{gid // 1_000_000}{gid // 1_000_000 + 1}"
    roster = {(r["teamId"], r["sweaterNumber"]): r["playerId"] for r in pbp.get("rosterSpots", [])}
    rows = []
    for code, team in (("TH", pbp["homeTeam"]), ("TV", pbp["awayTeam"])):
        page = get_text(TOI_HTML.format(season, code, str(gid)[4:]))
        if not page:
            return []
        player = None
        for chunk in re.split(r"(?=<td[^>]*playerHeading)", page):
            m = re.match(r'<td[^>]*playerHeading[^>]*>\s*(\d+)\s', chunk)
            if m:
                player = roster.get((team["id"], int(m.group(1))))
            if player is None:
                continue
            for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", chunk, re.S):
                c = [html.unescape(re.sub("<[^>]+>", "", x)).strip() for x in _CELL.findall(tr)]
                # Shift rows only; the per-period summary under each player
                # also starts with a number but has no "elapsed / game" pair.
                if len(c) < 5 or not c[0].isdigit() or "/" not in c[2] or "/" not in c[3]:
                    continue
                per = 4 if c[1] == "OT" else int(c[1]) if c[1].isdigit() else None
                if per is None:
                    continue
                start, end = c[2].split("/")[0].strip(), c[3].split("/")[0].strip()
                rows.append({"playerId": player, "teamId": team["id"], "period": per,
                             "startTime": start.zfill(5), "endTime": end.zfill(5),
                             "typeCode": 517})
    return rows


def get(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "xgcalc-backfill/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404 or i == tries - 1:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if i == tries - 1:
                raise
        time.sleep(2 ** i)


def save(path, obj):
    tmp = path.with_suffix(".tmp")
    with gzip.open(tmp, "wt") as f:
        json.dump(obj, f, separators=(",", ":"))
    tmp.replace(path)


def load(path):
    with gzip.open(path, "rt") as f:
        return json.load(f)


def season_id(year):
    return f"{year}{year + 1}"


def final_games(year):
    """Official games. The stats API can leave a game at OVER for hours after
    the play-by-play calls it official (OFF), so a game it has at OVER counts
    once its play-by-play says OFF; that play-by-play is cached on the way,
    and one that isn't OFF yet is never cached (a cached file is never
    fetched again)."""
    games = [g for g in get(GAMES.format(season_id(year)))["data"] if g["gameType"] in GAME_TYPES]
    ids = {g["id"] for g in games if g["gameStateId"] == FINAL}
    d = CACHE / str(year)
    for g in games:
        if g["gameStateId"] != OVER:
            continue
        p = d / f"{g['id']}.pbp.json.gz"
        if p.exists():
            ids.add(g["id"])
            continue
        try:
            pbp = get(PBP.format(g["id"]))
        except Exception:
            continue   # the next run asks again
        if pbp.get("gameState") == "OFF":
            save(p, pbp)
            ids.add(g["id"])
    return sorted(ids)


def fetch_game(year, gid):
    """Fetch what's missing for one game. Returns (pbp_fetched, shifts_state)."""
    d = CACHE / str(year)
    pbp_path, sh_path = d / f"{gid}.pbp.json.gz", d / f"{gid}.shifts.json.gz"
    got_pbp = False
    if not pbp_path.exists():
        save(pbp_path, get(PBP.format(gid)))
        got_pbp = True
    if sh_path.exists() and load(sh_path).get("data"):
        return got_pbp, "cached"
    shifts = get(SHIFTS.format(gid))
    if not shifts.get("data"):
        rows = shifts_from_html(gid, load(pbp_path))
        if rows:
            shifts = {"data": rows, "total": len(rows), "source": "html"}
    save(sh_path, shifts)
    return got_pbp, "ok" if shifts.get("data") else "empty"


def backfill_season(year, workers, refresh_bios):
    d = CACHE / str(year)
    d.mkdir(parents=True, exist_ok=True)
    for kind in ("skater", "goalie"):
        p = d / f"bios_{kind}.json.gz"
        if refresh_bios or not p.exists():
            bios = get(BIOS.format(kind, season_id(year)))
            # The API lists the same players in a different order each call;
            # sorted, the file only changes when a bio does, so the sheets
            # workflow doesn't take every run for new data.
            bios["data"] = sorted(bios.get("data", []), key=lambda r: r["playerId"])
            save(p, bios)

    games = final_games(year)
    todo = [g for g in games
            if not (d / f"{g}.pbp.json.gz").exists() or not (d / f"{g}.shifts.json.gz").exists()
            or not load(d / f"{g}.shifts.json.gz").get("data")]
    print(f"{year}-{(year + 1) % 100:02d}: {len(games)} final games, {len(todo)} to fetch",
          flush=True)
    fetched, empty, failed = 0, [], []
    t0 = time.time()
    with ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(fetch_game, year, g): g for g in todo}
        for i, f in enumerate(as_completed(futs), 1):
            g = futs[f]
            try:
                got, sh = f.result()
                fetched += got
                if sh == "empty":
                    empty.append(g)
            except Exception as e:  # keep going; the next run retries it
                failed.append((g, repr(e)))
            if i % 200 == 0:
                print(f"  {i}/{len(todo)}  {time.time() - t0:.0f}s", flush=True)
    print(f"  done: {fetched} new play-by-play, {len(empty)} empty shift charts, "
          f"{len(failed)} failed", flush=True)
    for g, e in failed[:10]:
        print(f"    failed {g}: {e}", file=sys.stderr)
    return {"games": len(games), "empty_shifts": empty, "failed": [g for g, _ in failed]}


def parse_seasons(spec):
    out = []
    for part in spec:
        if "-" in part:
            a, b = part.split("-")
            out += range(int(a), int(b) + 1)
        else:
            out.append(int(part))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seasons", nargs="+", required=True,
                    help="start years, e.g. 2015-2025 or 2024 2025")
    ap.add_argument("--workers", type=int, default=6,
                    help="parallel requests (default 6; be polite)")
    ap.add_argument("--refresh-bios", action="store_true",
                    help="re-download bios (do this for the season in progress)")
    a = ap.parse_args()
    report = {}
    for y in parse_seasons(a.seasons):
        report[y] = backfill_season(y, a.workers, a.refresh_bios)
    (CACHE / "last_backfill.json").write_text(json.dumps(report, indent=1))
    if any(r["failed"] for r in report.values()):
        sys.exit("Some games failed; run again to retry them.")


if __name__ == "__main__":
    main()
