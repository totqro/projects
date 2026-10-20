"use client";

import * as React from "react";
import Link from "next/link";
import { f1, f2, pct, sv, toi, toiMin } from "@/lib/format";
import { posLabel } from "@/lib/teams";
import type { GoalieSeason, Phase, PlayersFile, SkaterSeason } from "@/lib/types";
import { Signed, SortTable, type Column } from "@/components/tables/sortable";
import { Button } from "@/components/ui/button";
import { SearchInput } from "@/components/ui/search-input";
import { SelectField } from "@/components/site/field";
import { Note } from "@/components/site/section";
import { Segmented } from "@/components/teams/teams-view";

const rank: Column<never> = { k: "#", label: "#", cell: (_, i) => <span className="text-muted-foreground">{i + 1}</span>, className: "w-px" };
const nameCol = <R extends { id: number; name: string }>(label: string): Column<R> =>
  ({ k: "name", label, l: true, get: p => p.name, asc: true, cell: p => <Link href={`/player/${p.id}`} className="font-medium hover:underline">{p.name}</Link> });
const teamCol = <R extends { team: string }>(season: number): Column<R> =>
  ({ k: "team", label: "Team", l: true, get: p => p.team, asc: true, cell: p => p.team ? <Link href={`/team/${season}/${p.team}`} className="hover:underline">{p.team}</Link> : "" });

const skCols = (season: number): Column<SkaterSeason>[] => [
  rank as Column<SkaterSeason>, nameCol("Skater"), teamCol(season),
  { k: "pos", label: "Pos", l: true, get: p => posLabel(p.pos), asc: true, cell: p => posLabel(p.pos) },
  { k: "gp", label: "GP", get: p => p.gp, tip: "gp" },
  { k: "toi", label: "TOI/GP", get: p => p.toi / p.gp, cell: p => toi(p.toi / p.gp), tip: "toi" },
  { k: "g", label: "G", get: p => p.g, tip: "g" },
  { k: "a", label: "A", get: p => p.a, tip: "a" },
  { k: "pts", label: "P", get: p => p.pts, cell: p => <b className="font-semibold">{p.pts}</b>, tip: "p" },
  { k: "ixg", label: "ixG", get: p => p.ixg, cell: p => f1(p.ixg), tip: "ixg" },
  { k: "gax", label: "GAx", get: p => p.gax, cell: p => <Signed v={p.gax} />, tip: "gax" },
  { k: "att", label: "Att", get: p => p.att, tip: "att" },
  { k: "xgs", label: "xG share", get: p => p.xgf_pct, cell: p => pct(p.xgf_pct), tip: "xgs" },
  { k: "xgs5", label: "5v5 xG share", get: p => p.xgf_pct5, cell: p => pct(p.xgf_pct5), tip: "xgs5" },
  { k: "ixg60_5", label: "5v5 ixG/60", get: p => p.ixg60_5, cell: p => f2(p.ixg60_5), tip: "ixg60" },
  { k: "xgf60_5", label: "5v5 xGF/60", get: p => p.xgf60_5, cell: p => f2(p.xgf60_5), tip: "xgf60" },
  { k: "xga60_5", label: "5v5 xGA/60", get: p => p.xga60_5, cell: p => f2(p.xga60_5), asc: true, tip: "xga60" },
];
const gkCols = (season: number): Column<GoalieSeason>[] => [
  rank as Column<GoalieSeason>, nameCol("Goalie"), teamCol(season),
  { k: "gp", label: "GP", get: p => p.gp, tip: "gp" },
  { k: "toi", label: "Min", get: p => p.toi, cell: p => toiMin(p.toi), tip: "toitot" },
  { k: "sa", label: "Shots", get: p => p.sa, tip: "sa" },
  { k: "ga", label: "GA", get: p => p.ga, asc: true, tip: "gaG" },
  { k: "xga", label: "xGA", get: p => p.xga, cell: p => f1(p.xga), tip: "xgaG" },
  { k: "gsax", label: "GSAx", get: p => p.gsax, cell: p => <b className="font-semibold"><Signed v={p.gsax} /></b>, tip: "gsax" },
  { k: "gsax60", label: "GSAx/60", get: p => p.gsax60, cell: p => <Signed v={p.gsax60} d={2} />, tip: "gsax60" },
  { k: "sv_pct", label: "Sv%", get: p => p.sv_pct, cell: p => sv(p.sv_pct), tip: "svp" },
  { k: "xsv_pct", label: "xSv%", get: p => p.xsv_pct, cell: p => sv(p.xsv_pct), tip: "xsvp" },
];

const POS_OPTS: [string, string][] = [["", "All"], ["F", "Forwards"], ["C", "C"], ["L", "LW"], ["R", "RW"], ["D", "D"]];

export function PlayersView({ season, data, teams }: { season: number; data: Pick<PlayersFile, "regular" | "playoff">; teams: string[] }) {
  const [kind, setKind] = React.useState<"skaters" | "goalies">("skaters");
  const [phase, setPhase] = React.useState<Phase>("regular");
  const [team, setTeam] = React.useState("");
  const [pos, setPos] = React.useState("");
  const [minGp, setMinGp] = React.useState(1);
  const [minMin, setMinMin] = React.useState(100);
  const [q, setQ] = React.useState("");
  const [shown, setShown] = React.useState(100);
  const goalies = kind === "goalies";
  const hasPlayoffs = data.playoff.skaters.length > 0;

  const filt = <R extends { team: string; pos: string; toi: number; gp: number; name: string }>(rows: R[]) => {
    let r = rows;
    if (team) r = r.filter(p => p.team === team);
    if (!goalies && pos) r = r.filter(p => (pos === "D" ? p.pos === "D" : pos === "F" ? p.pos !== "D" : p.pos === pos));
    r = r.filter(p => (p.toi || 0) >= minMin * 60 && p.gp >= minGp);
    if (q) { const s = q.toLowerCase(); r = r.filter(p => p.name.toLowerCase().includes(s)); }
    return r;
  };
  const sk = React.useMemo(() => filt(data[phase].skaters), [data, phase, team, pos, minGp, minMin, q]); // eslint-disable-line react-hooks/exhaustive-deps
  const gk = React.useMemo(() => filt(data[phase].goalies), [data, phase, team, minGp, minMin, q]); // eslint-disable-line react-hooks/exhaustive-deps
  const skC = React.useMemo(() => skCols(season), [season]);
  const gkC = React.useMemo(() => gkCols(season), [season]);
  const count = goalies ? gk.length : sk.length;

  return (
    <>
      <div className="mb-5 flex flex-wrap items-end gap-3">
        <Segmented label="Players" value={kind} onChange={v => { setKind(v); setShown(100); }} options={[["skaters", "Skaters"], ["goalies", "Goalies"]]} />
        {hasPlayoffs && <Segmented label="Season phase" value={phase} onChange={setPhase} options={[["regular", "Regular season"], ["playoff", "Playoffs"]]} />}
        <SelectField label="Team" value={team} onChange={setTeam} options={[["", "All teams"], ...teams]} />
        {!goalies && <SelectField label="Position" value={pos} onChange={setPos} options={POS_OPTS} />}
        <SelectField label="Min. games" value={minGp} onChange={v => setMinGp(+v)} options={[1, 5, 10, 20, 40]} />
        <SelectField label="Min. minutes" value={minMin} onChange={v => setMinMin(+v)} options={[0, 100, 300, 600, 1000]} />
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          Search
          <SearchInput value={q} onChange={e => setQ(e.target.value)} onClear={() => setQ("")} placeholder="Name" className="h-9 w-44 text-sm" />
        </label>
        <span className="pb-2 text-sm text-muted-foreground">{count} {kind}</span>
      </div>
      {goalies
        ? <SortTable key="g" rows={gk} cols={gkC} initial={{ sort: "gsax", asc: false }} rowKey={p => p.id} limit={shown} />
        : <SortTable key="s" rows={sk} cols={skC} initial={{ sort: "pts", asc: false }} rowKey={p => p.id} limit={shown} />}
      {count > shown && <Button variant="secondary" className="mt-4" onClick={() => setShown(s => s + 200)}>Show more</Button>}
      <Note className="mt-4">
        {goalies
          ? "GSAx compares goals allowed with the xG of the unblocked shots a goalie faced. It needs a big sample: a full season of starts swings by ±5 on luck alone."
          : "Small samples mislead: a 20-shot sample of GAx is mostly noise. On-ice numbers credit everyone on the ice, so they reflect linemates and usage as much as the player."}{" "}
        Hover a heading for what it means.
      </Note>
    </>
  );
}
