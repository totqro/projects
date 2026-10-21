"use client";

import * as React from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { f2, fmtDate, longDate } from "@/lib/format";
import type { GameSummary } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SelectField } from "@/components/site/field";
import { Note } from "@/components/site/section";
import { TeamLogo } from "@/components/site/team-logo";

export const isUpset = (x: GameSummary) => x.hs !== x.as && (x.hxg >= x.axg) !== (x.hs > x.as);

/** A mini box score: the line score a paper prints for every game. */
export function MiniBox({ x }: { x: GameSummary }) {
  const status = x.end === "REG" ? "Final" : "F/" + x.end;
  const flags = [x.type === 3 ? "Playoffs" : "", isUpset(x) ? "−xG win" : ""].filter(Boolean);
  const line = (ab: string, s: number, xg: number, sog: number, won: boolean) => (
    <tr className={cn(won ? "font-semibold text-foreground" : "text-secondary-foreground")}>
      <td className="py-1 text-left"><span className="inline-flex items-center gap-2"><TeamLogo team={ab} size={26} />{ab}</span></td>
      <td className={cn("py-1 text-right", won && "brand-text")}>{s}</td>
      <td className="py-1 text-right text-muted-foreground">{f2(xg)}</td>
      <td className="py-1 text-right text-muted-foreground">{sog}</td>
    </tr>
  );
  return (
    <Link href={`/game/${x.id}`} aria-label={`${x.away} ${x.as}, ${x.home} ${x.hs}, ${fmtDate(x.date)}`}
      className="block rounded-[0.75rem] bg-card px-3.5 pb-3 pt-2.5 [box-shadow:var(--shadow-md)] transition-[background-color,box-shadow] hover:bg-accent/60 hover:[box-shadow:var(--shadow-lg)]">
      <table className="tabular w-full text-[13px]">
        <thead>
          <tr className="border-b border-border text-xs text-muted-foreground">
            <th className="pb-1.5 text-left font-normal">{fmtDate(x.date)} <span className="font-medium text-brand">{status}</span></th>
            <th className="pb-1.5 text-right font-normal">G</th>
            <th className="pb-1.5 text-right font-normal">xG</th>
            <th className="pb-1.5 text-right font-normal">SOG</th>
          </tr>
        </thead>
        <tbody>
          {line(x.away, x.as, x.axg, x.asog, x.as > x.hs)}
          {line(x.home, x.hs, x.hxg, x.hsog, x.hs > x.as)}
        </tbody>
      </table>
      <div className="mt-2 flex min-h-5 items-center justify-between gap-2">
        <span className="flex gap-1">{flags.map(f => <Badge key={f} variant={f === "Playoffs" ? "default" : "warning"}>{f}</Badge>)}</span>
        <span className="flex h-1.5 w-20 gap-px overflow-hidden rounded-full [box-shadow:var(--shadow-inset)]" title={`xG ${f2(x.axg)}–${f2(x.hxg)}`}>
          <i className="block bg-away" style={{ flex: x.axg }} />
          <i className="block bg-home" style={{ flex: x.hxg }} />
        </span>
      </div>
    </Link>
  );
}

function byDate(games: GameSummary[]) {
  const out: { date: string; games: GameSummary[] }[] = [];
  for (const x of games) {
    const last = out[out.length - 1];
    if (last && last.date === x.date) last.games.push(x); else out.push({ date: x.date, games: [x] });
  }
  return out;
}

type Sort = "date" | "lopsided" | "total" | "stole";
const winXg = (x: GameSummary) => (x.hs > x.as ? x.hxg - x.axg : x.axg - x.hxg);
const SORTS: Record<Sort, (a: GameSummary, b: GameSummary) => number> = {
  date: (a, b) => (b.date + b.id).localeCompare(a.date + a.id),
  lopsided: (a, b) => Math.abs(b.hxg - b.axg) - Math.abs(a.hxg - a.axg),
  total: (a, b) => b.hxg + b.axg - (a.hxg + a.axg),
  stole: (a, b) => winXg(a) - winXg(b),
};

export function GamesView({ season, recent, total, dates, hasPlayoffs, teams, updated }: {
  season: number; recent: GameSummary[]; total: number; dates: string[]; hasPlayoffs: boolean; teams: string[]; updated: string;
}) {
  const [team, setTeam] = React.useState("");
  const [type, setType] = React.useState("all");
  const [sort, setSort] = React.useState<Sort>("date");
  const [date, setDate] = React.useState("");
  const [shown, setShown] = React.useState(recent.length);
  const [all, setAll] = React.useState<GameSummary[] | null>(null);
  const [failed, setFailed] = React.useState(false);
  const reset = <T,>(f: (v: T) => void) => (v: T) => { f(v); setShown(recent.length); };

  // The pre-rendered nights cover the default view; anything else needs the
  // whole season (app/data/[season]/games.json).
  const needAll = !!team || type !== "all" || sort !== "date" || !!date || shown > recent.length;
  React.useEffect(() => {
    if (!needAll || all) return;
    fetch(`/data/${season}/games.json`).then(r => (r.ok ? r.json() : Promise.reject(r.status)))
      .then(setAll).catch(() => setFailed(true));
  }, [needAll, all, season]);
  const games = all ?? recent;
  const loading = needAll && !all && !failed;

  const list = React.useMemo(() => {
    let g = games.slice();
    if (team) g = g.filter(x => x.home === team || x.away === team);
    if (type !== "all") g = g.filter(x => x.type === (type === "playoff" ? 3 : 2));
    if (date) g = g.filter(x => x.date === date);
    return g.sort(SORTS[sort]);
  }, [games, team, type, sort, date]);
  const visible = list.slice(0, shown);
  const groups = sort === "date" ? byDate(visible) : [{ date: null as string | null, games: visible }];
  const count = all || !needAll ? (needAll ? list.length : total) : null;

  return (
    <>
      <div className="mb-5 flex flex-wrap items-end gap-3">
        <SelectField label="Team" value={team} onChange={reset(setTeam)} options={[["", "All teams"], ...teams]} />
        {hasPlayoffs && (
          <SelectField label="Games" value={type} onChange={reset(setType)}
            options={[["all", "All"], ["regular", "Regular season"], ["playoff", "Playoffs"]]} />
        )}
        <SelectField label="Date" value={date} onChange={reset(setDate)} options={[["", "All dates"], ...dates.map(d => [d, fmtDate(d)] as [string, string])]} />
        <SelectField label="Sort" value={sort} onChange={reset(v => setSort(v as Sort))}
          options={[["date", "Newest"], ["lopsided", "Most lopsided xG"], ["total", "Most total xG"], ["stole", "−xG wins"]]} />
        <span className="pb-2 text-sm text-muted-foreground" aria-live="polite">{loading ? "Loading…" : count != null ? `${count} games` : ""}</span>
        <span className="ml-auto pb-2 text-xs text-muted-foreground">{updated}</span>
      </div>
      {groups.map(d => (
        <section key={d.date ?? "all"} className="mb-6">
          {d.date && <h2 className="mb-3 text-[17px] font-semibold tracking-[-0.015em]">{longDate(d.date)}</h2>}
          <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3">
            {d.games.map(x => <MiniBox key={x.id} x={x} />)}
          </div>
        </section>
      ))}
      {failed && <Note className="mb-4">Couldn&apos;t load the rest of the season. Reload the page to try again.</Note>}
      {(all ? list.length > shown : !needAll && total > recent.length) && (
        <Button variant="secondary" onClick={() => setShown(s => s + 60)}>Show more</Button>
      )}
      <Note className="mt-4">G goals, xG expected goals, SOG shots on goal. A −xG win is a win with fewer expected goals than the other team.</Note>
    </>
  );
}
