import type { Metadata } from "next";
import { currentSeason, gameIds, liveIds, liveSheet, rawSheet, tonight } from "@/lib/data";
import { unpack } from "@/lib/unpack";
import { fmtDate } from "@/lib/format";
import { liveStatus, recap } from "@/lib/game";
import { GameView } from "@/components/game/game-view";
import { GamePreview } from "@/components/game/preview";

// Only this season's games are pre-rendered. Older seasons are served as JSON
// (app/data/[season]/game/[id]/route.ts) and drawn in the browser by
// app/game/archive, which firebase.json rewrites their /game/<id> URLs to.
// Tonight's games get a page before their official sheet: the sheet so far
// (data/live, pipeline/nhl_live.py) once there are shots, a preview before.
export const dynamicParams = false;
export function generateStaticParams() {
  const s = currentSeason();
  const ids = new Set([...gameIds(s), ...liveIds(), ...(tonight()?.games ?? []).map(g => g.id)]);
  return [...ids].filter(id => Math.floor(id / 1e6) === s).map(id => ({ id: String(id) }));
}

type Props = { params: Promise<{ id: string }> };

/** What a game's page shows: its official sheet, its sheet so far, or the
 *  preview from tonight's slate. */
function page(id: number) {
  if (gameIds(currentSeason()).includes(id)) return { raw: rawSheet(id) };
  if (liveIds().includes(id)) return { raw: liveSheet(id) };
  const t = tonight()!;
  return { game: t.games.find(g => g.id === id)!, date: t.date };
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const p = page(+(await params).id);
  if (p.game) {
    const g = p.game;
    return { title: `${g.away.abbrev} at ${g.home.abbrev} (${fmtDate(p.date)}), preview`,
      description: `${g.away.abbrev} at ${g.home.abbrev}: both teams' expected goals, special teams and goaltending this season.` };
  }
  const G = unpack(p.raw);
  const r = recap(G);
  const title = `${G.away.abbrev} ${G.away.score}, ${G.home.abbrev} ${G.home.score} (${fmtDate(G.date)})`;
  // A game scored so far keeps the site's share card: its own is drawn once it's final.
  if (G.live) return { title: `${title}, ${liveStatus(G.live, G.end)}`, description: `${r.headline}. ${r.text}` };
  // Share cards come from scripts/og-images.tsx, one per game this season.
  const image = { url: `/og/${G.id}.png`, width: 1200, height: 630, alt: `${G.away.abbrev} ${G.away.score}, ${G.home.abbrev} ${G.home.score}: final score and expected goals` };
  return {
    title, description: `${r.headline}. ${r.text}`,
    openGraph: { type: "article", title: r.headline, description: r.text, images: [image] },
    twitter: { card: "summary_large_image", title: r.headline, description: r.text, images: [image] },
  };
}

export default async function GamePage({ params }: Props) {
  const p = page(+(await params).id);
  return p.game ? <GamePreview g={p.game} date={p.date} /> : <GameView raw={p.raw} />;
}
