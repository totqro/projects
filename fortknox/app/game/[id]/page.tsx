import type { Metadata } from "next";
import Link from "next/link";
import { currentSeason, gameIds, rawSheet, seasonOfGame, seasons } from "@/lib/data";
import { unpack } from "@/lib/unpack";
import { fmtDate } from "@/lib/format";
import { recap } from "@/lib/game";
import { FlowChart } from "@/components/charts/flow";
import { BestChances, Scoring, ShotMap, ShotProvider } from "@/components/game/shots";
import { GameRoster } from "@/components/game/roster";
import { Periods, Recap, ScoreCard, Stars } from "@/components/game/sections";
import { Note, Panel, Section } from "@/components/site/section";

export const dynamicParams = false;
export function generateStaticParams() {
  return seasons().flatMap(s => gameIds(s).map(id => ({ id: String(id) })));
}

type Props = { params: Promise<{ id: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const G = unpack(rawSheet((await params).id));
  const r = recap(G);
  const title = `${G.away.abbrev} ${G.away.score}, ${G.home.abbrev} ${G.home.score} (${fmtDate(G.date)})`;
  // Share cards come from scripts/og-images.tsx: one per game this season,
  // the site card for older games.
  const image = seasonOfGame(G.id) === currentSeason()
    ? { url: `/og/${G.id}.png`, width: 1200, height: 630, alt: `${G.away.abbrev} ${G.away.score}, ${G.home.abbrev} ${G.home.score}: final score and expected goals` }
    : { url: "/og/site.png", width: 1200, height: 630, alt: "Fort Knox" };
  return {
    title, description: `${r.headline}. ${r.text}`,
    openGraph: { type: "article", title: r.headline, description: r.text, images: [image] },
    twitter: { card: "summary_large_image", title: r.headline, description: r.text, images: [image] },
  };
}

export default async function GamePage({ params }: Props) {
  const raw = rawSheet((await params).id);
  const G = unpack(raw);
  const season = +String(G.id).slice(0, 4);
  return (
    <ShotProvider raw={raw}>
      <Link href={`/games/${season}`} className="mb-4 inline-block text-sm text-muted-foreground hover:text-foreground">&larr; All games</Link>
      <Recap G={G} />
      <ScoreCard G={G} />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        <ShotMap />
        <div className="min-w-0 space-y-4">
          <Panel title="xG over the game">
            <FlowChart shots={G.shots} home={G.home.abbrev} away={G.away.abbrev} />
            <Note className="mt-2 text-xs">Cumulative expected goals; dots are goals. Steep stretches are where a team was generating chances.</Note>
          </Panel>
          <Panel title="Three stars"><Stars G={G} /></Panel>
        </div>
      </div>
      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Section title="Best chances"><BestChances n={6} /></Section>
        <Section title="Scoring"><Scoring /></Section>
        <Section title="By period"><Periods G={G} /></Section>
      </div>
      <div className="mt-8 grid gap-6 xl:grid-cols-2">
        <Section title={<span className="text-away">{G.away.name}</span>}>
          <GameRoster players={G.players.filter(p => p.team === G.away.abbrev)} />
        </Section>
        <Section title={<span className="text-home">{G.home.name}</span>}>
          <GameRoster players={G.players.filter(p => p.team === G.home.abbrev)} />
        </Section>
      </div>
      <Note className="mt-3">Hover a column heading for what it means. Time on ice comes from the NHL shift chart.</Note>
    </ShotProvider>
  );
}
