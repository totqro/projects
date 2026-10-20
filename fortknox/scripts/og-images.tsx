// Draws the share cards into public/og/: <id>.png for every game of the
// current season, and site.png for everything else (older games and every
// other page). app/game/[id]/page.tsx and app/layout.tsx name them as
// og:image. Runs as `prebuild`, so `npm run build` always ships them.
//
// Only the current season, because a card costs ~80 ms (mostly resvg's
// rasterising and PNG encoding) and ~80 KB: every season would add a minute
// of build and 120 MB per season kept. Older games are rarely shared.
//
// Done here rather than with an opengraph-image.tsx route: under
// output: "export" that route takes ~0.2 s a card (Next's wasm renderer) and
// writes an extension-less file Firebase would not serve as image/png. Native
// resvg is ~3x faster a card and runs across a few processes.
//
// Output depends only on the season index, so unchanged games give
// byte-identical files and do not re-upload on deploy.

import { fork } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import satori from "satori";
import { Resvg } from "@resvg/resvg-js";
import { GameCard, OG_SIZE, ogFonts, SiteCard } from "../lib/og";
import type { GameSummary, SeasonIndex } from "../lib/types";

const DATA = path.join(process.cwd(), "data");
const OUT = path.join(process.cwd(), "public/og");

/** The current season's games (seasons.json lists newest first). */
function games(): GameSummary[] {
  const { seasons } = JSON.parse(fs.readFileSync(path.join(DATA, "seasons.json"), "utf8")) as { seasons: number[] };
  return (JSON.parse(fs.readFileSync(path.join(DATA, `${seasons[0]}/index.json`), "utf8")) as SeasonIndex).games;
}

async function png(card: React.ReactNode, file: string) {
  const svg = await satori(card, { ...OG_SIZE, fonts: ogFonts() });
  fs.writeFileSync(path.join(OUT, file), new Resvg(svg).render().asPng());
}

async function draw(list: GameSummary[]) {
  for (const G of list) await png(<GameCard G={G} />, `${G.id}.png`);
}

async function main() {
  const [shard, of] = process.argv.slice(2).map(Number);
  const all = games();
  if (of) return draw(all.filter((_, i) => i % of === shard));

  const t0 = Date.now();
  fs.rmSync(OUT, { recursive: true, force: true });
  fs.mkdirSync(OUT, { recursive: true });
  await png(<SiteCard />, "site.png");
  const n = Math.max(1, Math.min(os.availableParallelism(), 8));
  await Promise.all(Array.from({ length: n }, (_, i) => new Promise<void>((ok, fail) => {
    fork(process.argv[1], [String(i), String(n)])
      .on("exit", code => (code === 0 ? ok() : fail(new Error(`og-images shard ${i} exited ${code}`))));
  })));
  console.log(`og-images: site card + ${all.length} game cards in ${((Date.now() - t0) / 1000).toFixed(1)}s (${n} processes)`);
}

main().catch(e => { console.error(e); process.exit(1); });
