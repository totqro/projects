"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { cn } from "@/lib/utils";
import { f1, f2, pct, per60, seasonLabel, share, signed, sv, toi, toiMin } from "@/lib/format";
import { posLabel } from "@/lib/teams";
import { relXg } from "@/lib/season";
import type { GoalieSeason, PlayersFile, SkaterSeason } from "@/lib/types";
import { SearchInput } from "@/components/ui/search-input";
import { Note } from "@/components/site/section";
import { TeamLogo } from "@/components/site/team-logo";
import { TipHead } from "@/components/tables/sortable";
import { usePickedSeason } from "@/components/site/nav";

// Up to four players side by side for one regular season, each number with
// where it ranks among his position group (forwards, defence or goalies).

type Row = SkaterSeason | GoalieSeason;
const isGoalie = (p: Row): p is GoalieSeason => p.pos === "G";
const group = (p: Row) => (p.pos === "G" ? "G" : p.pos === "D" ? "D" : "F");
const GROUP = { F: "forwards", D: "defencemen", G: "goalies" } as const;
const MAX = 4;

interface Stat<R> {
  label: string;
  tip?: string;
  /** The value shown. */
  show: (p: R) => string;
  /** The value ranked: a rate for counting stats, so games played don't decide it. Null leaves the row unranked. */
  rank: ((p: R) => number | null) | null;
  /** Lower is better. */
  low?: boolean;
  /** Ranked per game. */
  pg?: boolean;
}

const perGp = (v: number, p: { gp: number }) => (p.gp ? v / p.gp : null);
const SKATER: Stat<SkaterSeason>[] = [
  { label: "Games", tip: "gp", show: p => String(p.gp), rank: null },
  { label: "TOI per game", tip: "toi", show: p => toi(p.toi / p.gp), rank: p => perGp(p.toi, p) },
  { label: "Goals", pg: true, tip: "g", show: p => String(p.g), rank: p => perGp(p.g, p) },
  { label: "Assists", pg: true, tip: "a", show: p => String(p.a), rank: p => perGp(p.a, p) },
  { label: "Points", pg: true, tip: "p", show: p => String(p.pts), rank: p => perGp(p.pts, p) },
  { label: "ixG", pg: true, tip: "ixg", show: p => f1(p.ixg), rank: p => perGp(p.ixg, p) },
  { label: "Goals above expected", tip: "gax", show: p => signed(p.gax), rank: p => p.gax },
  { label: "5v5 ixG/60", tip: "ixg60", show: p => f2(p.ixg60_5), rank: p => p.ixg60_5 },
  { label: "5v5 xGF/60", tip: "xgf60", show: p => f2(p.xgf60_5), rank: p => p.xgf60_5 },
  { label: "5v5 xGA/60", tip: "xga60", show: p => f2(p.xga60_5), rank: p => p.xga60_5, low: true },
  { label: "5v5 xG share", tip: "xgs5", show: p => pct(p.xgf_pct5), rank: p => p.xgf_pct5 },
  { label: "5v5 Rel xG%", tip: "rel", show: p => { const r = relXg(p); return r == null ? "–" : signed(r * 100); }, rank: relXg },
  { label: "5v5 goal share", tip: "gs5", show: p => pct(share(p.gf5, p.ga5)), rank: p => share(p.gf5, p.ga5) },
  { label: "5v5 GF/60", tip: "gf60", show: p => f2(per60(p.gf5, p.toi5)), rank: p => per60(p.gf5, p.toi5) },
  { label: "5v5 GA/60", tip: "ga60", show: p => f2(per60(p.ga5, p.toi5)), rank: p => per60(p.ga5, p.toi5), low: true },
];
const GOALIE: Stat<GoalieSeason>[] = [
  { label: "Games", tip: "gp", show: p => String(p.gp), rank: null },
  { label: "Minutes", tip: "toitot", show: p => toiMin(p.toi), rank: null },
  { label: "GSAx", tip: "gsax", show: p => signed(p.gsax), rank: p => p.gsax },
  { label: "GSAx/60", tip: "gsax60", show: p => signed(p.gsax60, 2), rank: p => p.gsax60 },
  { label: "Unbl. Sv%", tip: "svp", show: p => sv(p.sv_pct), rank: p => p.sv_pct },
  { label: "Unbl. xSv%", tip: "xsvp", show: p => sv(p.xsv_pct), rank: p => p.xsv_pct },
  { label: "xGA per 60", tip: "xgaG", show: p => f2(per60(p.xga, p.toi)), rank: p => per60(p.xga, p.toi), low: true },
];

/** Percentile of `v` within `pool` (0 worst, 1 best). */
function percentile(pool: number[], v: number, low?: boolean) {
  if (pool.length < 2) return null;
  const worse = pool.filter(x => (low ? x > v : x < v)).length, same = pool.filter(x => x === v).length;
  return (worse + (same - 1) / 2) / (pool.length - 1);
}

export function CompareView({ current }: { current: number }) {
  const router = useRouter();
  const params = useSearchParams();
  const season = usePickedSeason() ?? current;
  const ids = React.useMemo(() => (params.get("p") ?? "").split(",").map(Number).filter(Boolean).slice(0, MAX), [params]);
  const [file, setFile] = React.useState<{ season: number; data: Pick<PlayersFile, "regular"> } | null>(null);
  const [err, setErr] = React.useState(false);
  const [q, setQ] = React.useState("");

  React.useEffect(() => {
    let live = true;
    setErr(false);
    fetch(`/data/${season}/players.json`).then(r => (r.ok ? r.json() : Promise.reject(r.status)))
      .then(data => live && setFile({ season, data }), () => live && setErr(true));
    return () => { live = false; };
  }, [season]);

  const all: Row[] = React.useMemo(() => (file ? [...file.data.regular.skaters, ...file.data.regular.goalies] : []), [file]);
  const byId = React.useMemo(() => new Map(all.map(p => [p.id, p])), [all]);
  const picked = ids.map(id => byId.get(id)).filter((p): p is Row => !!p);
  const missing = file ? ids.filter(id => !byId.has(id)) : [];
  const kind = picked[0] ? (isGoalie(picked[0]) ? "G" : "S") : null;

  const setIds = (next: number[]) => router.replace(next.length ? `/compare?p=${next.join(",")}` : "/compare", { scroll: false });
  const add = (id: number) => { setQ(""); if (!ids.includes(id) && ids.length < MAX) setIds([...ids, id]); };
  const drop = (id: number) => setIds(ids.filter(x => x !== id));

  const matches = React.useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return [];
    return all.filter(p => p.name.toLowerCase().includes(s) && !ids.includes(p.id) && (!kind || (kind === "G") === isGoalie(p)))
      .sort((a, b) => b.toi - a.toi).slice(0, 8);
  }, [q, all, ids, kind]);

  // Ranked among his group with at least half the games of its busiest player.
  const pools = React.useMemo(() => {
    const out = new Map<string, Row[]>();
    for (const g of ["F", "D", "G"]) {
      const rows = all.filter(p => group(p) === g), most = Math.max(1, ...rows.map(p => p.gp));
      out.set(g, rows.filter(p => p.gp >= most / 2));
    }
    return out;
  }, [all]);

  const stats = (kind === "G" ? GOALIE : SKATER) as Stat<Row>[];
  const cell = (s: Stat<Row>, p: Row) => {
    if (!s.rank) return { pc: null };
    const v = s.rank(p);
    if (v == null) return { pc: null };
    const pool = pools.get(group(p))!.map(s.rank).filter((x): x is number => x != null);
    return { v, pc: percentile(pool, v, s.low) };
  };

  return (
    <>
      <div className="mb-6 flex flex-wrap items-end gap-3">
        <label className="relative flex flex-col gap-1 text-xs text-muted-foreground">
          {ids.length >= MAX ? `Up to ${MAX} players` : kind === "G" ? "Add a goalie" : kind ? "Add a skater" : "Add a player"}
          <SearchInput value={q} onChange={e => setQ(e.target.value)} onClear={() => setQ("")} placeholder="Name" disabled={ids.length >= MAX || !file}
            className="h-9 w-64 text-sm" onKeyDown={e => { if (e.key === "Enter" && matches[0]) add(matches[0].id); }} />
          {matches.length > 0 && (
            <ul role="listbox" className="absolute left-0 top-full z-40 mt-1 w-72 overflow-hidden rounded-md border border-border bg-popover py-1 text-sm text-foreground [box-shadow:var(--shadow-l)]">
              {matches.map(p => (
                <li key={p.id} role="option" aria-selected={false}>
                  <button type="button" onClick={() => add(p.id)} className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-muted">
                    <TeamLogo team={p.team} size={18} />
                    <span className="font-medium">{p.name}</span>
                    <span className="ml-auto text-xs text-muted-foreground">{posLabel(p.pos)}, {p.gp} GP</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </label>
        <span className="pb-2 text-sm text-muted-foreground">{seasonLabel(season)} regular season</span>
      </div>

      {err && <Note>Couldn&apos;t load {seasonLabel(season)}&apos;s players.</Note>}
      {missing.length > 0 && <Note className="mb-3">{missing.length === 1 ? "One player" : `${missing.length} players`} picked didn&apos;t play in {seasonLabel(season)}; pick another season above.</Note>}
      {!picked.length && file && <Note>Search for a player to start, then add up to {MAX - 1} more to set beside him.</Note>}

      {picked.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[480px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="w-44" />
                {picked.map(p => (
                  <th key={p.id} className="px-3 pb-3 text-left align-bottom font-normal">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <Link href={`/player/${p.id}`} className="font-semibold hover:underline">{p.name}</Link>
                        <div className="mt-0.5 flex items-center gap-1.5 text-xs text-muted-foreground"><TeamLogo team={p.team} size={16} />{p.team}, {posLabel(p.pos)}</div>
                      </div>
                      <button type="button" onClick={() => drop(p.id)} aria-label={`Remove ${p.name}`} className="rounded px-1.5 text-muted-foreground hover:text-foreground">×</button>
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {stats.map(s => {
                const cells = picked.map(p => cell(s, p));
                const vs = cells.flatMap(c => (c.v == null ? [] : [c.v]));
                const best = picked.length > 1 && vs.length > 1 ? (s.low ? Math.min(...vs) : Math.max(...vs)) : null;
                return (
                  <tr key={s.label} className="border-b border-border/60">
                    <TipHead tip={s.tip} className="py-2 pr-3 text-left text-xs font-normal text-muted-foreground">{s.label}</TipHead>
                    {picked.map((p, i) => {
                      const c = cells[i];
                      return (
                        <td key={p.id} className="px-3 py-2 align-top">
                          <div className={cn("tabular", c.v != null && c.v === best ? "font-semibold text-brand" : "")}>{s.show(p)}</div>
                          {c.pc != null && (
                            <div className="mt-1 flex items-center gap-2" title={`Better than ${Math.round(c.pc * 100)}% of ${GROUP[group(p)]}${s.pg ? ", per game" : ""}`}>
                              <div className="h-1 w-20 overflow-hidden rounded-full bg-muted">
                                <div className="h-full rounded-full" style={{ width: `${Math.max(3, c.pc * 100)}%`, background: c.pc >= 0.67 ? "var(--good)" : c.pc <= 0.33 ? "var(--bad)" : "var(--muted-foreground)" }} />
                              </div>
                              <span className="tabular text-[11px] text-muted-foreground">{Math.round(c.pc * 100)}{s.pg && c.v != null && <> · {c.v.toFixed(2)}/gp</>}</span>
                            </div>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {picked.length > 0 && (
        <Note className="mt-4">
          The bar under each number is its percentile among {kind === "G" ? "goalies" : "forwards or defencemen (by the player's position)"} with at least half as many games as the busiest of them: 100 is the best in the league. Goals, assists, points, ixG and ice time are ranked per game, so games played don&apos;t decide them. The best number in each row is highlighted.
        </Note>
      )}
    </>
  );
}
