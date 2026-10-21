"use client";

import * as React from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { longDate, pct } from "@/lib/format";
import type { TonightGame } from "@/lib/types";
import { Note } from "@/components/site/section";
import { TeamLogo } from "@/components/site/team-logo";
import { gameColors } from "@/lib/team-colors";

/** Season-to-date numbers for a team, from its teams.json row. */
export type Form = { xg5: number; gsax: number };

/** The slate's date in ET, rolled over at 6am (scripts/fetch-tonight.mjs). */
const slateDate = (now = new Date()) =>
  new Date(now.getTime() - 6 * 3600e3).toLocaleDateString("en-CA", { timeZone: "America/New_York" });

const startTime = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: "America/New_York" }) + " ET";

const signed = (v: number) => (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(1);

function Card({ g, form, sheet }: { g: TonightGame; form: Record<string, Form>; sheet: boolean }) {
  const final = g.state === "final";
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
            <TeamLogo team={t.abbrev} size={26} /><span className={cn(won && "font-semibold")}>{t.abbrev}</span>
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
      {final && (
        <div className="mt-2 text-xs text-muted-foreground">
          {sheet ? <span className="font-medium text-brand">Game sheet →</span> : "Sheet once the shift charts are in"}
        </div>
      )}
    </>
  );
  const cls = "block rounded-[0.75rem] bg-card px-3.5 pb-3 pt-2.5 [box-shadow:var(--shadow-md)]";
  return sheet ? (
    <Link href={`/game/${g.id}`} style={gameColors(g.away.abbrev, g.home.abbrev)} aria-label={`${g.away.abbrev} ${g.away.score}, ${g.home.abbrev} ${g.home.score}, game sheet`}
      className={cn(cls, "transition-[background-color,box-shadow] hover:bg-accent/60 hover:[box-shadow:var(--shadow-lg)]")}>
      {body}
    </Link>
  ) : <div className={cls}>{body}</div>;
}

/** Tonight's games above the feed: puck drop in ET, then In progress, then
 *  the final with a link once the sheet is up. Hidden once every game has its
 *  sheet (the feed below has them), and in a browser whose clock says the
 *  slate is stale (before the first run of a new day redeploys the site). */
export function TonightStrip({ date, games, form, sheets }: {
  date: string; games: TonightGame[]; form: Record<string, Form>; sheets: number[];
}) {
  const [stale, setStale] = React.useState(false);
  React.useEffect(() => setStale(slateDate() !== date), [date]);
  const has = new Set(sheets);
  if (stale || !games.length || games.every(g => g.state === "off" || has.has(g.id))) return null;
  return (
    <section aria-labelledby="tonight-h" className="mb-8">
      <h2 id="tonight-h" className="mb-3 text-[17px] font-semibold tracking-[-0.015em]">
        Tonight <span className="font-normal text-muted-foreground">· {longDate(date)}</span>
      </h2>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3">
        {games.map(g => <Card key={g.id} g={g} form={form} sheet={has.has(g.id)} />)}
      </div>
      <Note className="mt-3">Season to date: 5v5 xG% is each team&apos;s share of expected goals at 5-on-5, GSAx its goalies&apos; goals saved above expected.</Note>
    </section>
  );
}
