import Link from "next/link";
import type { RawSheet } from "@/lib/types";
import { unpack } from "@/lib/unpack";
import { gameColors } from "@/lib/team-colors";
import { FlowChart } from "@/components/charts/flow";
import { BestChances, Scoring, ShotMap, ShotProvider } from "@/components/game/shots";
import { GameRoster } from "@/components/game/roster";
import { Periods, Recap, ScoreCard, Stars } from "@/components/game/sections";
import { Note, Panel, Section } from "@/components/site/section";

/** A whole game page from its sheet. Rendered on the server for this season's
 *  pre-rendered games and in the browser for older ones (archived-game.tsx). */
export function GameView({ raw }: { raw: RawSheet }) {
  const G = unpack(raw);
  const season = +String(G.id).slice(0, 4);
  // The shot map only needs names; the rosters below get the full lines.
  // Sending the full player table twice was a third of every game page.
  const slim = { ...raw, players: raw.players.map(({ id, name, team, pos, num }) => ({ id, name, team, pos, num })) };
  return (
    <ShotProvider raw={slim}>
      {/* Each team in its own colours: everything below reads --away / --home. */}
      <div style={gameColors(G.away.abbrev, G.home.abbrev)}>
        <Link href={`/games/${season}`} className="mb-4 inline-block text-sm text-muted-foreground hover:text-foreground">&larr; All games</Link>
        <ScoreCard G={G} />
        <Recap G={G} />
        <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
          <div className="min-w-0 space-y-4">
            <ShotMap />
            <Section title="By period"><Periods G={G} /></Section>
          </div>
          <div className="min-w-0 space-y-4">
            <Panel title="xG over the game">
              <FlowChart shots={G.shots} home={G.home.abbrev} away={G.away.abbrev} />
              <Note className="mt-2 text-xs">Running total of expected goals. Dots are goals.</Note>
            </Panel>
            <Panel title="Three stars"><Stars G={G} /></Panel>
          </div>
        </div>
        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          <Section title="Best chances"><BestChances n={6} /></Section>
          <Section title="Scoring"><Scoring /></Section>
        </div>
        <div className="mt-8 grid gap-6 xl:grid-cols-2">
          <Section title={<span className="text-away">{G.away.name}</span>}>
            <GameRoster players={G.players.filter(p => p.team === G.away.abbrev)} />
          </Section>
          <Section title={<span className="text-home">{G.home.name}</span>}>
            <GameRoster players={G.players.filter(p => p.team === G.home.abbrev)} />
          </Section>
        </div>
      </div>
    </ShotProvider>
  );
}
