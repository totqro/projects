"use client";

import * as React from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import type { ProjTeam } from "@/lib/projections";
import { SortTable, Signed, type Column } from "@/components/tables/sortable";
import { Segmented } from "@/components/teams/teams-view";
import { TeamLogo } from "@/components/site/team-logo";
import { Section } from "@/components/site/section";

type Grouping = "conference" | "division" | "league";
type Row = ProjTeam & { rk: number; cut?: boolean };

/** 0.004 to "<1%", 0.996 to ">99%", else whole percents. */
function odds(p: number) {
  if (p === 0) return "–";
  if (p < 0.005) return "<1%";
  if (p > 0.995 && p < 1) return ">99%";
  return `${Math.round(p * 100)}%`;
}

/** A probability on a tint of the good colour, deeper the likelier. */
function Odds({ p, bold }: { p: number; bold?: boolean }) {
  const depth = p < 0.005 ? 0 : Math.round(8 + p * 40);
  return (
    <span className={cn("tabular -my-0.5 inline-block min-w-[3.2rem] rounded-[2px] px-1.5 py-0.5 text-right", bold && "font-semibold")}
      style={{ background: depth ? `color-mix(in oklch, var(--good) ${depth}%, transparent)` : undefined }}>
      {odds(p)}
    </span>
  );
}

/** The 10th-90th percentile of final points as a bar on a scale shared by
 *  every row, with a tick at the average. */
function Range({ t, min, max }: { t: ProjTeam; min: number; max: number }) {
  const W = 132, H = 14, X = (v: number) => 2 + ((v - min) / (max - min)) * (W - 4);
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${t.lo} to ${t.hi} points`} className="inline-block align-middle">
      <title>{`80% of simulated seasons end between ${t.lo} and ${t.hi} points`}</title>
      <line x1={2} x2={W - 2} y1={H / 2} y2={H / 2} stroke="var(--border)" />
      <rect x={X(t.lo)} width={Math.max(2, X(t.hi) - X(t.lo))} y={3} height={H - 6} rx={2}
        fill="color-mix(in oklch, var(--brand) 38%, transparent)" />
      <line x1={X(t.proj)} x2={X(t.proj)} y1={1} y2={H - 1} stroke="var(--brand)" strokeWidth={2.5} />
    </svg>
  );
}

const cols = (season: number, min: number, max: number): Column<Row>[] => [
  { k: "rk", label: "#", get: t => t.rk, asc: true, cell: t => <span className="text-muted-foreground">{t.rk}</span> },
  {
    k: "team", label: "Team", l: true, pin: true, get: t => t.team, asc: true,
    cell: t => <Link href={`/team/${season}/${t.team}`} className="flex w-[4.25rem] items-center gap-2.5 font-medium hover:underline"><TeamLogo team={t.team} size={26} />{t.team}</Link>,
  },
  { k: "gp", label: "GP", get: t => t.gp, tip: "gp" },
  { k: "pts", label: "PTS", get: t => t.pts, tip: "Points so far." },
  { k: "proj", label: "Proj", get: t => t.proj, cell: t => <b className="font-semibold">{t.proj.toFixed(0)}</b>, tip: "Projected final points: the average over every simulated season." },
  { k: "range", label: "80% range", get: t => t.hi - t.lo, cell: t => <span className="inline-flex items-center gap-2"><span className="w-[3.75rem] text-right text-muted-foreground">{t.lo}–{t.hi}</span><Range t={t} min={min} max={max} /></span>, tip: "Final points in the middle 80% of simulated seasons: one in ten ends below the bar, one in ten above it.", wide: true },
  { k: "playoff", label: "Playoffs", get: t => t.playoff, cell: t => <Odds p={t.playoff} bold />, tip: "Share of simulated seasons in which the team makes the playoffs: top three in its division or one of its conference's two wild cards." },
  { k: "divwin", label: "Div. title", get: t => t.divwin, cell: t => <Odds p={t.divwin} />, tip: "Share of simulated seasons in which the team wins its division." },
  { k: "pres", label: "Presidents'", get: t => t.pres, cell: t => <Odds p={t.pres} />, tip: "Share of simulated seasons in which the team finishes first in the league.", more: true },
  { k: "xgd", label: "5v5 xGD/GP", get: t => t.xgd, cell: t => <Signed v={t.xgd} d={2} />, tip: "5-on-5 expected goals for minus against, per game so far: half of what the projection rates a team on.", wide: true },
  { k: "elo", label: "Elo", get: t => t.elo, cell: t => t.elo.toFixed(0), tip: "Elo rating from every result since 2014-15 (1500 is average): the other half of the rating.", more: true },
];

function groups(rows: ProjTeam[], g: Grouping): { title: string | null; rows: Row[] }[] {
  const byOdds = (a: ProjTeam, b: ProjTeam) => b.playoff - a.playoff || b.proj - a.proj;
  const rank = (rs: ProjTeam[], cutAt?: number) =>
    rs.slice().sort(byOdds).map((t, i) => ({ ...t, rk: i + 1, cut: cutAt != null && i === cutAt - 1 }));
  if (g === "league") return [{ title: null, rows: rank(rows) }];
  if (g === "conference")
    return (["East", "West"] as const).map(c => ({ title: `${c}ern Conference`, rows: rank(rows.filter(t => t.conf === c), 8) }));
  return ["Atlantic", "Metropolitan", "Central", "Pacific"].map(d => ({ title: `${d} Division`, rows: rank(rows.filter(t => t.div === d), 3) }));
}

export function PlayoffsView({ season, teams }: { season: number; teams: ProjTeam[] }) {
  const [g, setG] = React.useState<Grouping>("conference");
  const min = Math.min(...teams.map(t => t.lo)) - 2, max = Math.max(...teams.map(t => t.hi)) + 2;
  const c = React.useMemo(() => cols(season, min, max), [season, min, max]);
  return (
    <div className="space-y-8">
      <Segmented value={g} onChange={setG} label="Group teams by" tabs
        options={[["conference", "Conference"], ["division", "Division"], ["league", "League"]]} />
      <div className="grid gap-8">
        {groups(teams, g).map(grp => (
          <Section key={grp.title ?? "league"} title={grp.title ?? "League"}>
            <div className="overflow-x-auto">
              <SortTable rows={grp.rows} cols={c} initial={{ sort: "rk", asc: true }} rowKey={t => t.team}
                rowProps={t => ({ className: cn(t.cut && "cut") })} csv={`playoff-odds-${season}`}
                hide={g === "division" ? new Set(["pres", "elo"]) : undefined} />
            </div>
          </Section>
        ))}
      </div>
    </div>
  );
}
