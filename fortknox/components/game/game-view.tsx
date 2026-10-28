import type { LiveInfo, RawSheet } from "@/lib/types";
import { unpack } from "@/lib/unpack";
import { gameColors } from "@/lib/team-colors";
import { FlowChart } from "@/components/charts/flow";
import { BestChances, Scoring, ShotMap, ShotProvider } from "@/components/game/shots";
import { GameRoster } from "@/components/game/roster";
import { Periods, Recap, ScoreCard, Stars } from "@/components/game/sections";
import { Note, Panel, Section } from "@/components/site/section";
import { BackLink } from "@/components/site/trail";
import { DeserveToWin } from "@/components/game/deserve";

const etTime = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: "America/New_York" }) + " ET";

/** Above a game scored before its official sheet: how old the numbers are,
 *  and that they'll be replaced. */
function LiveBanner({ live }: { live: LiveInfo }) {
  const on = live.state === "live";
  return (
    <div role="status" className="mb-4 flex flex-wrap items-baseline gap-x-2 gap-y-1 rounded-lg border border-border bg-card px-3.5 py-2.5 text-sm">
      <span className="inline-flex items-center gap-1.5 font-semibold text-brand">
        {on && <span className="inline-block size-2 rounded-full bg-brand" aria-hidden="true" />}
        {on ? "In progress" : "Final, provisional"}
      </span>
      <span className="text-muted-foreground">
        {on
          ? `Shots through ${etTime(live.updated)}. The sheet updates about every 20 minutes while the game is on.`
          : `Scored at ${etTime(live.updated)}. The official sheet${live.shifts ? "" : ", with ice time,"} replaces this one within the hour, and its numbers can move a little.`}
      </span>
    </div>
  );
}

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
        <BackLink key={G.id} href={`/games/${season}`} label="All games" className="mb-4 inline-block max-w-full truncate align-top text-sm text-muted-foreground hover:text-foreground" />
        {G.live && <LiveBanner live={G.live} />}
        <ScoreCard G={G} />
        <Recap G={G} />
        <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
          <div className="min-w-0 space-y-4">
            <ShotMap />
            <Section title="By period"><Periods G={G} /></Section>
          </div>
          <div className="min-w-0 space-y-4">
            <Panel title={G.live?.state === "live" ? "Deserve to win, so far" : "Deserve to win"}><DeserveToWin G={G} /></Panel>
            <Panel title="xG over the game">
              <FlowChart shots={G.shots} home={G.home.abbrev} away={G.away.abbrev} />
              <Note className="mt-2 text-xs">Running total of expected goals. Dots are goals.</Note>
            </Panel>
            <Panel title={G.live?.state === "live" ? "Stars so far" : "Three stars"}><Stars G={G} /></Panel>
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
