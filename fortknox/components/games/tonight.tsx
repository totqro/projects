"use client";

import * as React from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { longDate, pct } from "@/lib/format";
import type { GameSummary, TonightGame } from "@/lib/types";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { TeamLogo } from "@/components/site/team-logo";
import { gameColors } from "@/lib/team-colors";
import { MiniBox } from "./games-view";
import { slateDate } from "./slate";

/** Season-to-date numbers for a team, from its teams.json row. */
export type Form = { xg5: number; gsax: number };


const startTime = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: "America/New_York" }) + " ET";

const signed = (v: number) => (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(1);

/** A game with no shots on its sheet yet: puck drop (or the score) and each
 *  team's season form. Opens the preview (app/game/[id]) when `page` is set;
 *  a season not published yet has none. */
function Card({ g, form, page }: { g: TonightGame; form: Record<string, Form>; page: boolean }) {
  const final = g.state === "final";
  const season = String(g.id).slice(0, 4);
  const status =
    g.state === "pre" ? startTime(g.start)
    : g.state === "live" ? "In progress"
    : g.state === "off" ? "Postponed"
    : g.end && g.end !== "REG" ? `Final/${g.end}` : "Final";
  const row = (t: TonightGame["away"], won: boolean) => {
    const f = form[t.abbrev];
    return (
      <tr className={final && !won ? "text-secondary-foreground" : "text-foreground"}>
        <td className="whitespace-nowrap py-1 text-left">
          <span className="inline-flex items-center gap-2">
            <Link href={`/team/${season}/${t.abbrev}`} className="relative z-[2] inline-flex items-center gap-2 underline-offset-2 hover:underline">
              <TeamLogo team={t.abbrev} size={26} /><span className={cn(won && "font-semibold")}>{t.abbrev}</span>
            </Link>
            {t.record && <span className="text-xs font-normal text-muted-foreground">{t.record}</span>}
          </span>
        </td>
        {final && <td className={cn("py-1 text-right", won && "brand-text font-semibold")}>{t.score}</td>}
        <td className="py-1 text-right text-muted-foreground">{f ? pct(f.xg5) : "–"}</td>
        <td className="py-1 text-right text-muted-foreground">{f ? signed(f.gsax) : "–"}</td>
      </tr>
    );
  };
  const aw = final && (g.away.score ?? 0) > (g.home.score ?? 0), hw = final && (g.home.score ?? 0) > (g.away.score ?? 0);
  const body = (
    <>
      <table className="tabular w-full text-[13px]">
        <thead>
          <tr className="border-b border-border text-xs text-muted-foreground">
            <th className="pb-1.5 text-left font-normal">
              <span className={cn("font-medium", g.state === "pre" ? "text-foreground" : "text-brand")}>
                {g.state === "live" && <span className="mr-1.5 inline-block size-1.5 -translate-y-px rounded-full bg-brand align-middle" />}
                {status}
              </span>
            </th>
            {final && <th className="pb-1.5 text-right font-normal">G</th>}
            <th className="pb-1.5 text-right font-normal">5v5 xG%</th>
            <th className="pb-1.5 text-right font-normal">GSAx</th>
          </tr>
        </thead>
        <tbody>
          {row(g.away, aw)}
          {row(g.home, hw)}
        </tbody>
      </table>
      {page && g.state !== "off" ? (
        <div className="mt-2 text-xs font-medium text-brand">Preview →</div>
      ) : final && (
        <div className="mt-2 text-xs text-muted-foreground">Sheet once the shift charts are in</div>
      )}
    </>
  );
  const cls = "block rounded-[0.75rem] bg-card px-3.5 pb-3 pt-2.5 [box-shadow:var(--shadow-md)]";
  // The whole card opens the game, by way of a link stretched over it; the
  // team names sit above that link (a link can't hold links).
  return page && g.state !== "off" ? (
    <div style={gameColors(g.away.abbrev, g.home.abbrev)}
      className={cn(cls, "relative transition-[background-color,box-shadow] hover:bg-accent/60 hover:[box-shadow:var(--shadow-lg)]")}>
      <Link href={`/game/${g.id}`} aria-label={`${g.away.abbrev} at ${g.home.abbrev}: preview`} className="absolute inset-0 z-[1] rounded-[inherit]" />
      {body}
    </div>
  ) : <div className={cls}>{body}</div>;
}

/** A game's box score once its sheet has shots: the official one, or the
 *  sheet so far with `live` its state ("2nd 11:13"). */
export interface Box { x: GameSummary; live?: string }

/** Every one of tonight's games in puck-drop order, the feed's own date
 *  section for the slate: a preview card until a game has shots, then its box
 *  score, live and then final. The feed below leaves these games out
 *  (games-view.tsx) until a browser's clock says the slate is stale, before
 *  the first run of a new day redeploys the site; then this hides instead. */
export function TonightStrip({ date, games, form, boxes, pages }: {
  date: string; games: TonightGame[]; form: Record<string, Form>; boxes: Record<number, Box>; pages: boolean;
}) {
  const [stale, setStale] = React.useState(false);
  React.useEffect(() => setStale(slateDate() !== date), [date]);
  if (stale || !games.length) return null;
  const order = games.slice().sort((a, b) => a.start.localeCompare(b.start) || a.id - b.id);
  return (
    <section aria-labelledby="tonight-h" className="mb-8">
      <h2 id="tonight-h" className="mb-3 text-[17px] font-semibold tracking-[-0.015em]">
        Tonight <span className="font-normal text-muted-foreground">· {longDate(date)}</span>
        <Popover>
          <PopoverTrigger aria-label="About these cards"
            className="ml-1.5 inline-grid size-5 -translate-y-px place-items-center rounded-full align-middle text-muted-foreground hover:text-foreground">
            <svg viewBox="0 0 20 20" className="size-4" aria-hidden="true">
              <circle cx="10" cy="10" r="8.2" fill="none" stroke="currentColor" strokeWidth="1.5" />
              <path d="M10 9v5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              <circle cx="10" cy="6.2" r="1" fill="currentColor" />
            </svg>
          </PopoverTrigger>
          <PopoverContent align="start" className="w-72 text-[13px] font-normal leading-relaxed tracking-normal text-secondary-foreground">
            Before a game: 5v5 xG% is each team&apos;s season share of expected goals at 5-on-5, GSAx its goalies&apos; goals saved
            above expected. Once it starts, the card shows the sheet so far, updated about every 20 minutes.
          </PopoverContent>
        </Popover>
      </h2>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3">
        {order.map(g => boxes[g.id]
          ? <MiniBox key={g.id} x={boxes[g.id].x} live={boxes[g.id].live} />
          : <Card key={g.id} g={g} form={form} page={pages} />)}
      </div>
    </section>
  );
}
