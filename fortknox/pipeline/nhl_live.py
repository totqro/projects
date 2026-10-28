#!/usr/bin/env python3
"""Game sheets for tonight's games in progress, and for finished games whose
official sheet isn't built yet, so the site can show the xG so far.

  python nhl_live.py --sheets DIR      rewrites DIR/live/{game_id}.json

Each file is a game sheet in the same shape as {season}/games/{id}.json, plus
a "live" block (state, period, clock, when it was scored). The games go
through nhl_sheets.build in a scratch folder, so they never touch the season
tables. A game leaves live/ once its official sheet is published; nhl_sheets.py
builds that one with the full shift chart, so its numbers can move a little.

The shift chart lags a live game, often by the whole game, and the model
scores shots without it the way it scores old games that never got one:
fatigue features are left blank. Players' ice time is missing until then too.

A file is only rewritten when the game changed (a new shot, period or
clock), so a quiet run leaves live/ as it was. With GITHUB_OUTPUT set, it
writes changed=true|false there.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import nhl_backfill  # noqa: E402
from nhl_sheets import build, current_season  # noqa: E402

SCORE = "https://api-web.nhle.com/v1/score/{}"
LIVE, DONE = {"LIVE", "CRIT"}, {"FINAL", "OFF"}
SHOT_KINDS = {"goal", "shot-on-goal", "missed-shot", "blocked-shot"}


def slate_date(now=None):
    """The slate's date in ET, rolled over at 6am, as fetch-tonight.mjs has it."""
    now = now or datetime.now(timezone.utc)
    return (now - timedelta(hours=6)).astimezone(ZoneInfo("America/New_York")).date().isoformat()


def candidates(date):
    """Tonight's games that have started: (id, gameState)."""
    games = nhl_backfill.get(SCORE.format(date)).get("games", [])
    return [(g["id"], g["gameState"]) for g in games
            if g.get("gameType") in (2, 3) and g.get("gameState") in LIVE | DONE]


def live_block(pbp, state):
    clock = pbp.get("clock") or {}
    period = (pbp.get("periodDescriptor") or {})
    return {"state": "final" if state in DONE else "live",
            "period": period.get("number"), "period_type": period.get("periodType"),
            "clock": clock.get("timeRemaining"), "intermission": bool(clock.get("inIntermission")),
            "updated": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def same(a, b):
    """Two live sheets match apart from when they were scored."""
    strip = lambda s: {**s, "live": {k: v for k, v in s["live"].items() if k != "updated"}}
    return strip(a) == strip(b)


def run(sheets, date):
    season = current_season()
    live_dir = sheets / "live"
    old = {int(p.stem): json.loads(p.read_text()) for p in live_dir.glob("*.json")} if live_dir.exists() else {}
    new = {}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        raw = tmp / "cache" / str(season)
        raw.mkdir(parents=True)
        # Handedness, age and height come from the season's bios.
        for kind in ("skater", "goalie"):
            b = nhl_backfill.CACHE / str(season) / f"bios_{kind}.json.gz"
            if b.exists():
                shutil.copy(b, raw / b.name)
        states = {}
        for gid, state in candidates(date):
            if gid // 1_000_000 != season or (sheets / str(season) / "games" / f"{gid}.json").exists():
                continue
            pbp = nhl_backfill.get(nhl_backfill.PBP.format(gid))
            if not any(p.get("typeDescKey") in SHOT_KINDS for p in pbp.get("plays", [])):
                continue   # no shots yet: the site shows the preview
            try:
                shifts = nhl_backfill.get(nhl_backfill.SHIFTS.format(gid))
            except Exception:
                shifts = {"data": []}
            nhl_backfill.save(raw / f"{gid}.pbp.json.gz", pbp)
            nhl_backfill.save(raw / f"{gid}.shifts.json.gz", shifts)
            states[gid] = (state, live_block(pbp, state), bool(shifts.get("data")))
        if states:
            build(season, tmp / "out", fetch=False, cache=tmp / "cache")
            for gid, (state, block, has_shifts) in states.items():
                sheet = json.loads((tmp / "out" / str(season) / "games" / f"{gid}.json").read_text())
                sheet["live"] = {**block, "shifts": has_shifts}
                new[gid] = old[gid] if gid in old and same(old[gid], sheet) else sheet

    changed = set(new) != set(old) or any(new[g] is not old.get(g) for g in new)
    if live_dir.exists():
        shutil.rmtree(live_dir)
    if new:
        live_dir.mkdir(parents=True)
        for gid, sheet in new.items():
            (live_dir / f"{gid}.json").write_text(json.dumps(sheet, separators=(",", ":")))
    for gid, s in sorted(new.items()):
        L = s["live"]
        print(f"{gid} {s['away']['abbrev']} {s['away']['score']} @ {s['home']['abbrev']} {s['home']['score']}: "
              f"{L['state']}, P{L['period']} {L['clock']}{' (int.)' if L['intermission'] else ''}, "
              f"xG {s['away']['xg']:.2f}-{s['home']['xg']:.2f}, shifts {L['shifts']}"
              f"{'' if new[gid] is not old.get(gid) else ' (unchanged)'}")
    print(f"live: {len(new)} games on {date}, {'changed' if changed else 'no change'}")
    return changed


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sheets", type=Path, required=True, help="the published sheets folder")
    ap.add_argument("--date", help="slate date, YYYY-MM-DD (default: tonight in ET)")
    a = ap.parse_args()
    changed = run(a.sheets, a.date or slate_date())
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"changed={'true' if changed else 'false'}\n")


if __name__ == "__main__":
    main()
