import type { LiveInfo, RawSheet } from "@/lib/types";
import { unpack } from "@/lib/unpack";
import { gameColors } from "@/lib/team-colors";
import { BestChances, Scoring, ShotMap, ShotProvider } from "@/components/game/shots";
import { GameRoster } from "@/components/game/roster";
import { Recap, ScoreCard, Stars } from "@/components/game/sections";
import { ChancesByPeriod, GamePercentiles, type GameRanks } from "@/components/game/detail";
import { Block } from "@/components/site/section";
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
export function GameView({ raw, ranks }: { raw: RawSheet; ranks?: GameRanks | null }) {
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
        {/* Who earned it, at a glance: the shots and what they were worth. */}
        <div className="grid items-start gap-x-10 gap-y-10 lg:grid-cols-[minmax(0,1.65fr)_minmax(0,1fr)]">
          <ShotMap />
          <Block title={G.live?.state === "live" ? "Deserve to win, so far" : "Deserve to win"}><DeserveToWin G={G} /></Block>
        </div>

        <Block title={G.live?.state === "live" ? "Stars so far" : "Three stars"} className="mt-10"><Stars G={G} /></Block>

        {/* Then the numbers behind it, a step down. */}
        <div className="mt-10 border-t-[3px] border-foreground pt-2">
          <h2 className="text-xs font-bold uppercase tracking-[0.14em] text-muted-foreground">In detail</h2>
        </div>
        <div className="mt-6 grid items-start gap-x-12 gap-y-10 lg:grid-cols-2">
          {ranks && <Block title="Game percentiles"><GamePercentiles G={G} ranks={ranks} /></Block>}
          <Block title="Chances by period"><ChancesByPeriod G={G} /></Block>
          <Block title="Goals"><Scoring /></Block>
          <Block title="Best chances"><BestChances n={5} /></Block>
        </div>
        <div className="mt-12 grid gap-x-12 gap-y-10 xl:grid-cols-2">
          <Block title={<span className="text-away">{G.away.name}</span>}>
            <GameRoster players={G.players.filter(p => p.team === G.away.abbrev)} />
          </Block>
          <Block title={<span className="text-home">{G.home.name}</span>}>
            <GameRoster players={G.players.filter(p => p.team === G.home.abbrev)} />
          </Block>
        </div>
      </div>
    </ShotProvider>
  );
}
