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
import { gameColors } from "@/lib/team-colors";
import { nickname, teamName } from "@/lib/teams";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { slateDate } from "./slate";
import { winnerChance } from "@/lib/deserve";

/** The winner's deserve-to-win, or null without one (lib/deserve.ts). */
const won = (x: GameSummary) => winnerChance(x.hs, x.as, x.dw);
/** A win the shots gave the winner under UPSET of a chance: a near coin
 *  flip isn't one. */
const UPSET = 0.4;
export const isUpset = (x: GameSummary) => (won(x) ?? 1) < UPSET;
const pct0 = (v: number) => `${Math.round(v * 100)}%`;

/** A mini box score: the line score a paper prints for every game. `live`
 *  is the state of a game still on ("2nd 11:13"), which drops the result
 *  flags and bolds the leader. */
export function MiniBox({ x, live }: { x: GameSummary; live?: string }) {
  const status = live ?? (x.end === "REG" ? "Final" : "F/" + x.end);
  const flags = [x.type === 3 ? "Playoffs" : "", !live && isUpset(x) ? `Won at ${pct0(won(x)!)}` : ""].filter(Boolean);
  const colors = gameColors(x.away, x.home);
  const season = String(x.id).slice(0, 4);
  // The xG numbers take the team colours the bar below uses, so the bar
  // reads without a legend.
  const line = (ab: string, s: number, xg: number, sog: number, won: boolean, xgCol: string) => (
    <tr className={cn(won ? "font-semibold text-foreground" : "text-secondary-foreground")}>
      <td className="py-1 text-left">
        <Link href={`/team/${season}/${ab}`} className="relative z-[2] inline-flex items-center gap-2 underline-offset-2 hover:underline">
          <TeamLogo team={ab} size={26} />{ab}
        </Link>
      </td>
      <td className={cn("py-1 text-right", won && "brand-text")}>{s}</td>
      <td className={cn("py-1 text-right", xgCol)}>{f2(xg)}</td>
      <td className="py-1 text-right text-muted-foreground">{sog}</td>
    </tr>
  );
  return (
    // The whole card opens the game, by way of a link stretched over it; the
    // team names and the xG bar sit above that link (a link can't hold links).
    <div style={colors}
      className="relative rounded-[0.75rem] bg-card px-3.5 pb-3 pt-2.5 [box-shadow:var(--shadow-md)] transition-[background-color,box-shadow] hover:bg-accent/60 hover:[box-shadow:var(--shadow-lg)]">
      <Link href={`/game/${x.id}`} aria-label={`${x.away} ${x.as}, ${x.home} ${x.hs}, ${fmtDate(x.date)}`} className="absolute inset-0 z-[1] rounded-[inherit]" />
      <table className="tabular w-full text-[13px]">
        <thead>
          <tr className="border-b border-border text-xs text-muted-foreground">
            <th className="pb-1.5 text-left font-normal">
              {live
                ? <span className="font-medium text-brand"><span className="mr-1.5 inline-block size-1.5 -translate-y-px rounded-full bg-brand align-middle" />{status}</span>
                : <>{fmtDate(x.date)} <span className="font-medium text-brand">{status}</span></>}
            </th>
            <th className="pb-1.5 text-right font-normal">G</th>
            <th className="pb-1.5 text-right font-normal">xG</th>
            <th className="pb-1.5 text-right font-normal">SOG</th>
          </tr>
        </thead>
        <tbody>
          {line(x.away, x.as, x.axg, x.asog, x.as > x.hs, "text-away")}
          {line(x.home, x.hs, x.hxg, x.hsog, x.hs > x.as, "text-home")}
        </tbody>
      </table>
      <div className="mt-2 flex min-h-5 items-center justify-between gap-2">
        <span className="flex gap-1">
          {flags.map(f => f === "Playoffs" ? <Badge key={f} variant="default">{f}</Badge> : (
            <Tooltip key={f} delayDuration={0}>
              <TooltipTrigger asChild>
                {/* above the card's stretched game link, so it can be hovered */}
                <span className="relative z-[2] cursor-help"><Badge variant="warning">{f}</Badge></span>
              </TooltipTrigger>
              <TooltipContent className="max-w-60 text-pretty leading-relaxed">
                Replay this game&apos;s shots, each one going in with its xG as the chance, and the {nickname(teamName(x.hs > x.as ? x.home : x.away))} win
                only {pct0(won(x)!)} of the time. They won anyway, on finishing or goaltending.
              </TooltipContent>
            </Tooltip>
          ))}
        </span>
        <Tooltip delayDuration={0}>
          <TooltipTrigger asChild>
            {/* padded so the hover target is bigger than the 6px bar */}
            <span className="relative z-[2] -my-2 py-2" aria-label={`Expected goals: ${teamName(x.away)} ${f2(x.axg)}, ${teamName(x.home)} ${f2(x.hxg)}`}>
              <span className="flex h-1.5 w-20 gap-px overflow-hidden rounded-full [box-shadow:var(--shadow-inset)]">
                <i className="block bg-away" style={{ flex: x.axg }} />
                <i className="block bg-home" style={{ flex: x.hxg }} />
              </span>
            </span>
          </TooltipTrigger>
          <TooltipContent style={colors} className="tabular">
            <div className="mb-0.5 text-muted-foreground">Expected goals</div>
            <div><b className="font-semibold text-away">{nickname(teamName(x.away))} {f2(x.axg)}</b></div>
            <div><b className="font-semibold text-home">{nickname(teamName(x.home))} {f2(x.hxg)}</b></div>
            {!live && x.dw != null && <>
              <div className="mb-0.5 mt-1.5 text-muted-foreground">Deserve to win</div>
              <div><b className="font-semibold text-away">{nickname(teamName(x.away))} {pct0(1 - x.dw)}</b></div>
              <div><b className="font-semibold text-home">{nickname(teamName(x.home))} {pct0(x.dw)}</b></div>
            </>}
          </TooltipContent>
        </Tooltip>
      </div>
    </div>
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
const SORTS: Record<Sort, (a: GameSummary, b: GameSummary) => number> = {
  date: (a, b) => (b.date + b.id).localeCompare(a.date + a.id),
  lopsided: (a, b) => Math.abs(b.hxg - b.axg) - Math.abs(a.hxg - a.axg),
  total: (a, b) => b.hxg + b.axg - (a.hxg + a.axg),
  stole: (a, b) => (won(a) ?? 1) - (won(b) ?? 1),
};

export function GamesView({ season, recent, total, dates, hasPlayoffs, teams, updated, slate, tonightSection }: {
  season: number; recent: GameSummary[]; total: number; dates: string[]; hasPlayoffs: boolean; teams: string[]; updated: string;
  /** The date the Tonight section above covers; its games are left out of
   *  the unfiltered feed while that section shows (components/games/tonight.tsx). */
  slate?: string;
  /** The Tonight section, drawn between the filters and the feed. */
  tonightSection?: React.ReactNode;
}) {
  const [team, setTeam] = React.useState("");
  const [type, setType] = React.useState("all");
  const [sort, setSort] = React.useState<Sort>("date");
  const [date, setDate] = React.useState("");
  const [shown, setShown] = React.useState(recent.length);
  const [all, setAll] = React.useState<GameSummary[] | null>(null);
  const [failed, setFailed] = React.useState(false);
  const reset = <T,>(f: (v: T) => void) => (v: T) => { f(v); setShown(recent.length); };
  // Tonight hides itself once the browser's clock has moved on to a new
  // slate; then the feed has those games again.
  const [tonight, setTonight] = React.useState(slate);
  React.useEffect(() => { if (slate && slateDate() !== slate) setTonight(undefined); }, [slate]);

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
    if (tonight && !team && !date && type === "all" && sort === "date") g = g.filter(x => x.date !== tonight);
    return g.sort(SORTS[sort]);
  }, [games, team, type, sort, date, tonight]);
  const visible = list.slice(0, shown);
  const groups = sort === "date" ? byDate(visible) : [{ date: null as string | null, games: visible }];
  const count = all || !needAll ? (needAll ? list.length : total) : null;

  return (
    <>
      <div className="mb-5 flex flex-wrap items-end gap-3">
        <SelectField label="Team" teams value={team} onChange={reset(setTeam)} options={[["", "All teams"], ...teams]} />
        {hasPlayoffs && (
          <SelectField label="Games" value={type} onChange={reset(setType)}
            options={[["all", "All"], ["regular", "Regular season"], ["playoff", "Playoffs"]]} />
        )}
        <SelectField label="Date" value={date} onChange={reset(setDate)} options={[["", "All dates"], ...dates.map(d => [d, fmtDate(d)] as [string, string])]} />
        <SelectField label="Sort" value={sort} onChange={reset(v => setSort(v as Sort))}
          options={[["date", "Newest"], ["lopsided", "Most lopsided xG"], ["total", "Most total xG"], ["stole", "Biggest upsets"]]} />
        <span className="pb-2 text-sm text-muted-foreground" aria-live="polite">{loading ? "Loading…" : count != null ? `${count} games` : ""}</span>
        <span className="ml-auto pb-2 text-xs text-muted-foreground">{updated}</span>
      </div>
      {tonightSection}
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
      <Note className="mt-4">G goals, xG expected goals, SOG shots on goal. “Won at 31%” marks a win the shots gave the winner only a 31% chance of: its deserve-to-win (hover the bar for both teams’).</Note>
    </>
  );
}
