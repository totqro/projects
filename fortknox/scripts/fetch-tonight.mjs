#!/usr/bin/env node
// Tonight's NHL slate for the home page strip, written to data/tonight.json.
// Run by scripts/fetch-data.sh, so every deploy carries a fresh copy;
// xg-game-sheets.yml redeploys when the slate changes (a new day, a puck
// drop, a final). "Tonight" runs until 6am ET, so late West games stay up
// until morning. Never fails the build: on any error the file is removed
// and the strip doesn't show.
//
// --sig prints a one-line summary of the slate (date and each game's state)
// instead, for the workflow to compare against its last run.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const OUT = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "data", "tonight.json");

/** The slate's date in ET, rolled over at 6am. Mirrored in components/games/tonight.tsx. */
export function slateDate(now = new Date()) {
  return new Date(now.getTime() - 6 * 3600e3).toLocaleDateString("en-CA", { timeZone: "America/New_York" });
}

const STATE = { FUT: "pre", PRE: "pre", LIVE: "live", CRIT: "live", FINAL: "final", OFF: "final" };

async function slate() {
  const date = slateDate();
  const res = await fetch(`https://api-web.nhle.com/v1/score/${date}`, { signal: AbortSignal.timeout(15000) });
  if (!res.ok) throw new Error(`NHL score ${date}: HTTP ${res.status}`);
  const body = await res.json();
  const side = t => ({ abbrev: t.abbrev, score: t.score ?? null, record: t.record ?? null });
  const games = (body.games ?? [])
    .filter(g => g.gameType === 2 || g.gameType === 3)
    .map(g => ({
      id: g.id,
      type: g.gameType,
      start: g.startTimeUTC,
      state: g.gameScheduleState !== "OK" ? "off" : STATE[g.gameState] ?? "pre",
      end: g.gameOutcome?.lastPeriodType ?? null,
      away: side(g.awayTeam),
      home: side(g.homeTeam),
    }));
  return { date, games };
}

if (process.argv[1] === fileURLToPath(import.meta.url) && process.argv[2] === "--sig") {
  const { date, games } = await slate();
  console.log([date, ...games.map(g => `${g.id}:${g.state}`)].join(" "));
} else if (process.argv[1] === fileURLToPath(import.meta.url)) {
  slate().then(({ date, games }) => {
    fs.writeFileSync(OUT, JSON.stringify({ date, fetched: new Date().toISOString(), games }));
    console.log(`tonight: ${date}, ${games.length} games`);
  }).catch(e => {
    fs.rmSync(OUT, { force: true });
    console.warn(`tonight: skipped (${e.message})`);
  });
}
