"use client";

import * as React from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { f1, f2, pct, share, sv } from "@/lib/format";
import { groupTeams, LENSES, type Grouping, type StandingRow } from "@/lib/season";
import { nickname, teamName } from "@/lib/teams";
import type { Phase } from "@/lib/types";
import { useLensChart } from "@/components/charts/lens";
import { Signed, SortTable, type Column } from "@/components/tables/sortable";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Note, Section } from "@/components/site/section";

type Row = StandingRow & { rk: string; cut?: boolean };

const cols = (season: number): Column<Row>[] => [
  { k: "std", label: "#", get: t => t.lg, asc: true, cell: t => <span className="text-muted-foreground">{t.rk}</span>, tip: "rank" },
  { k: "team", label: "Team", l: true, get: t => t.team, asc: true,
    cell: t => <Link href={`/team/${season}/${t.team}`} className="font-medium hover:underline">{t.team} <span className="font-normal text-muted-foreground">{nickname(teamName(t.team))}</span></Link> },
  { k: "gp", label: "GP", get: t => t.gp, tip: "gp" },
  { k: "w", label: "W", get: t => t.w, tip: "w" },
  { k: "l", label: "L", get: t => t.l, asc: true, tip: "l" },
  { k: "otl", label: "OTL", get: t => t.otl, tip: "otl" },
  { k: "pts", label: "PTS", get: t => t.pts, cell: t => <b className="font-semibold">{t.pts}</b>, tip: "pts" },
  { k: "ppct", label: "P%", get: t => t.ppct, cell: t => sv(t.ppct), tip: "ppct" },
  { k: "rw", label: "RW", get: t => t.rw, tip: "rw" },
  { k: "diff", label: "Diff", get: t => t.diff, cell: t => <Signed v={t.diff} d={0} />, tip: "diff" },
  { k: "xgf", label: "xGF", get: t => t.xgf, cell: t => f1(t.xgf), tip: "txgf" },
  { k: "xga", label: "xGA", get: t => t.xga, cell: t => f1(t.xga), asc: true, tip: "txga" },
  { k: "xgs", label: "xG share", get: t => share(t.xgf, t.xga), cell: t => pct(share(t.xgf, t.xga)), tip: "txgs" },
  { k: "xgs5", label: "5v5 xG share", get: t => t["5v5"].xgf_pct, cell: t => <b className="font-semibold">{pct(t["5v5"].xgf_pct)}</b>, tip: "txgs5" },
  { k: "xgf60", label: "5v5 xGF/60", get: t => t["5v5"].xgf60, cell: t => f2(t["5v5"].xgf60), tip: "txgf60" },
  { k: "xga60", label: "5v5 xGA/60", get: t => t["5v5"].xga60, cell: t => f2(t["5v5"].xga60), asc: true, tip: "txga60" },
  { k: "pp60", label: "PP xGF/60", get: t => t.pp.xgf60, cell: t => f2(t.pp.xgf60), tip: "pp60" },
  { k: "pk60", label: "PK xGA/60", get: t => t.pk.xga60, cell: t => f2(t.pk.xga60), asc: true, tip: "pk60" },
  { k: "gax", label: "GAx", get: t => t.gax, cell: t => <Signed v={t.gax} />, tip: "tgax" },
  { k: "gsax", label: "GSAx", get: t => t.gsax, cell: t => <Signed v={t.gsax} />, tip: "tgsax" },
];

export function Segmented<T extends string>({ value, onChange, options, label }: {
  value: T; onChange: (v: T) => void; options: [T, string][]; label: string;
}) {
  return (
    <ToggleGroup type="single" value={value} onValueChange={v => v && onChange(v as T)} aria-label={label} className="flex-wrap">
      {options.map(([k, l]) => <ToggleGroupItem key={k} value={k}>{l}</ToggleGroupItem>)}
    </ToggleGroup>
  );
}

export function TeamsView({ season, regular, playoff }: { season: number; regular: StandingRow[]; playoff: StandingRow[] }) {
  const [phase, setPhase] = React.useState<Phase>("regular");
  const [group, setGroup] = React.useState<Grouping>("league");
  const [lens, setLens] = React.useState("drive");
  const rows = phase === "playoff" ? playoff : regular;
  const chart = useLensChart({ rows, lens, season });
  const groups = groupTeams(rows, phase === "playoff" ? "league" : group);
  const columns = React.useMemo(() => cols(season), [season]);

  return (
    <>
      {playoff.length > 0 && (
        <div className="mb-5">
          <Segmented label="Season phase" value={phase} onChange={setPhase} options={[["regular", "Regular season"], ["playoff", "Playoffs"]]} />
        </div>
      )}

      <Card className="mb-8">
        <CardHeader className="gap-3 pb-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <CardTitle>Team lenses</CardTitle>
            <Segmented label="Lens" value={lens} onChange={setLens}
              options={Object.entries(LENSES).map(([k, l]) => [k, l.name] as [string, string])} />
          </div>
          <p className="max-w-3xl text-[13px] leading-relaxed text-muted-foreground">{LENSES[lens].desc}</p>
        </CardHeader>
        <CardContent className="grid gap-5 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
          <div>{chart.svg}</div>
          <div>
            {chart.callouts}
            <Note className="mt-3 text-xs">
              Lines split at the league average{lens === "luck" ? " (50% for shares)" : ""}. Hover a team for its numbers; click it to open the team.
            </Note>
          </div>
        </CardContent>
      </Card>

      {phase === "regular" && (
        <div className="mb-5">
          <Segmented label="Standings grouping" value={group} onChange={setGroup}
            options={[["league", "League"], ["conference", "Conference"], ["division", "Division"], ["wildcard", "Wild card"]]} />
        </div>
      )}
      <div className="space-y-6">
        {groups.map((g, i) => (
          <Section key={g.title ?? i} title={g.title ?? "Standings"}>
            <SortTable rows={g.rows} cols={columns} initial={{ sort: "std", asc: true }} naturalKey="std"
              rowKey={t => t.team} rowProps={t => ({ className: cn(t.cut && "border-b-2 border-b-[oklch(1_0_0/0.2)]") })} />
          </Section>
        ))}
      </div>
      <Note className="mt-4">
        Ranked by points, with the NHL&apos;s tiebreakers. Click a heading to re-sort and hover it for what it means.
        On 2025-26, a team&apos;s first-half 5v5 xG share predicted its second-half points better (r = 0.60) than its first-half goal share (0.42) or points (0.43).
      </Note>
    </>
  );
}
