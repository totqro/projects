import type { Metadata } from "next";
import { currentSeason, gameIds, rawSheet } from "@/lib/data";
import { unpack } from "@/lib/unpack";
import { fmtDate } from "@/lib/format";
import { recap } from "@/lib/game";
import { GameView } from "@/components/game/game-view";

// Only this season's games are pre-rendered. Older seasons are served as JSON
// (app/data/[season]/game/[id]/route.ts) and drawn in the browser by
// app/game/archive, which firebase.json rewrites their /game/<id> URLs to.
export const dynamicParams = false;
export function generateStaticParams() {
  return gameIds(currentSeason()).map(id => ({ id: String(id) }));
}

type Props = { params: Promise<{ id: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const G = unpack(rawSheet((await params).id));
  const r = recap(G);
  const title = `${G.away.abbrev} ${G.away.score}, ${G.home.abbrev} ${G.home.score} (${fmtDate(G.date)})`;
  // Share cards come from scripts/og-images.tsx, one per game this season.
  const image = { url: `/og/${G.id}.png`, width: 1200, height: 630, alt: `${G.away.abbrev} ${G.away.score}, ${G.home.abbrev} ${G.home.score}: final score and expected goals` };
  return {
    title, description: `${r.headline}. ${r.text}`,
    openGraph: { type: "article", title: r.headline, description: r.text, images: [image] },
    twitter: { card: "summary_large_image", title: r.headline, description: r.text, images: [image] },
  };
}

export default async function GamePage({ params }: Props) {
  return <GameView raw={rawSheet((await params).id)} />;
}
