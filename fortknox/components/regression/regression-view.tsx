"use client";

import * as React from "react";
import Link from "next/link";
import { f1, pct, share, sv } from "@/lib/format";
import { posLabel } from "@/lib/teams";
import type { StandingRow } from "@/lib/season";
import type { GoalieSeason, Phase, SkaterSeason } from "@/lib/types";
import { Signed, SortTable, type Column } from "@/components/tables/sortable";
import { Button } from "@/components/ui/button";
import { SelectField } from "@/components/site/field";
import { Note, Section } from "@/components/site/section";
import { Segmented } from "@/components/teams/teams-view";

// Who is ahead of or behind their chances. Shooting and save percentages
// swing a lot from game to game and drift back toward normal; expected goals
// settle down much sooner. So the gap between goals and xG is the part of a
// record that tends to fade.

/** A skater's or goalie's season, trimmed to what this page reads. */
export type RegSkater = Pick<SkaterSeason, "id" | "name" | "team" | "pos" | "gp" | "toi5" | "g" | "ixg" | "gax" | "att" | "sog" | "xgf5" | "xga5" | "gf5" | "ga5">;
export type RegGoalie = Pick<GoalieSeason, "id" | "name" | "team" | "gp" | "toi" | "sa" | "ga" | "xga" | "gsax" | "sv_pct" | "xsv_pct">;
export type RegTeam = Pick<StandingRow, "team" | "gp" | "pts" | "xgf" | "xga" | "gf_x" | "ga_x" | "gax" | "gsax">;
export interface RegPhase { teams: RegTeam[]; skaters: RegSkater[]; goalies: RegGoalie[] }

/** A share gap in percentage points: + is results ahead of the chances. */
const Gap = ({ v }: { v: number | null }) => (v == null ? <>{"–"}</> : <b className="font-semibold"><Signed v={v * 100} /></b>);
const gapOf = (gf: number, ga: number, xgf: number, xga: number) => {
  const g = share(gf, ga), x = share(xgf, xga);
  return g == null || x == null ? null : g - x;
};
const pace = (v: number, gp: number) => (gp ? (v / gp) * 82 : null);

const nameCol = <R extends { id: number; name: string }>(label: string): Column<R> =>
  ({ k: "name", label, l: true, pin: true, get: p => p.name, asc: true, cell: p => <Link href={`/player/${p.id}`} className="font-medium hover:underline">{p.name}</Link> });
const teamCol = <R extends { team: string }>(season: number): Column<R> =>
  ({ k: "team", label: "Team", l: true, get: p => p.team, asc: true, cell: p => p.team ? <Link href={`/team/${season}/${p.team}`} className="hover:underline">{p.team}</Link> : "" });

const teamCols = (season: number): Column<RegTeam>[] => [
  teamCol(season),
  { k: "gp", label: "GP", get: t => t.gp, tip: "gp" },
  { k: "pts", label: "Pts", get: t => t.pts, tip: "pts" },
  { k: "xgs", label: "xG share", get: t => share(t.xgf, t.xga), cell: t => pct(share(t.xgf, t.xga)), tip: "txgs" },
  { k: "gs", label: "G share", get: t => share(t.gf_x, t.ga_x), cell: t => pct(share(t.gf_x, t.ga_x)), tip: "tgs" },
  { k: "gap", label: "Gap", get: t => gapOf(t.gf_x, t.ga_x, t.xgf, t.xga), cell: t => <Gap v={gapOf(t.gf_x, t.ga_x, t.xgf, t.xga)} />, tip: "tgap" },
  { k: "gax", label: "Shooting GAx", get: t => t.gax, cell: t => <Signed v={t.gax} />, tip: "tgax" },
  { k: "gsax", label: "Goalies GSAx", get: t => t.gsax, cell: t => <Signed v={t.gsax} />, tip: "tgsax" },
];

const shooterCols = (season: number): Column<RegSkater>[] => [
  nameCol("Skater"), teamCol(season),
  { k: "pos", label: "Pos", l: true, get: p => posLabel(p.pos), asc: true, cell: p => posLabel(p.pos) },
  { k: "gp", label: "GP", get: p => p.gp, tip: "gp" },
  { k: "att", label: "Att", get: p => p.att, tip: "att" },
  { k: "g", label: "G", get: p => p.g, tip: "g" },
  { k: "ixg", label: "ixG", get: p => p.ixg, cell: p => f1(p.ixg), tip: "ixg" },
  { k: "gax", label: "GAx", get: p => p.gax, cell: p => <b className="font-semibold"><Signed v={p.gax} /></b>, tip: "gax" },
  { k: "shp", label: "Sh%", get: p => (p.sog ? p.g / p.sog : null), cell: p => pct(p.sog ? p.g / p.sog : null), tip: "shp" },
  { k: "gpace", label: "Goal pace", get: p => pace(p.g, p.gp), cell: p => f1(pace(p.g, p.gp)), tip: "gpace" },
  { k: "xpace", label: "xG pace", get: p => pace(p.ixg, p.gp), cell: p => f1(pace(p.ixg, p.gp)), tip: "xpace" },
];

const onIceGap = (p: RegSkater) => gapOf(p.gf5, p.ga5, p.xgf5, p.xga5);
const onIceCols = (season: number): Column<RegSkater>[] => [
  nameCol("Skater"), teamCol(season),
  { k: "pos", label: "Pos", l: true, get: p => posLabel(p.pos), asc: true, cell: p => posLabel(p.pos) },
  { k: "gp", label: "GP", get: p => p.gp, tip: "gp" },
  { k: "xgf", label: "xGF", get: p => p.xgf5, cell: p => f1(p.xgf5), tip: "xgf5" },
  { k: "gf", label: "GF", get: p => p.gf5, tip: "gf5" },
  { k: "xga", label: "xGA", get: p => p.xga5, cell: p => f1(p.xga5), asc: true, tip: "xga5" },
  { k: "ga", label: "GA", get: p => p.ga5, asc: true, tip: "ga5" },
  { k: "xgs5", label: "xG share", get: p => share(p.xgf5, p.xga5), cell: p => pct(share(p.xgf5, p.xga5)), tip: "xgs5" },
  { k: "gs5", label: "G share", get: p => share(p.gf5, p.ga5), cell: p => pct(share(p.gf5, p.ga5)), tip: "gs5" },
  { k: "gap", label: "Gap", get: onIceGap, cell: p => <Gap v={onIceGap(p)} />, tip: "gap5" },
];

const goalieCols = (season: number): Column<RegGoalie>[] => [
  nameCol("Goalie"), teamCol(season),
  { k: "gp", label: "GP", get: p => p.gp, tip: "gp" },
  { k: "sa", label: "Shots", get: p => p.sa, tip: "sa" },
  { k: "ga", label: "GA", get: p => p.ga, asc: true, tip: "gaG" },
  { k: "xga", label: "xGA", get: p => p.xga, cell: p => f1(p.xga), tip: "xgaG" },
  { k: "sv_pct", label: "Unbl. Sv%", get: p => p.sv_pct, cell: p => sv(p.sv_pct), tip: "svp" },
  { k: "xsv_pct", label: "Unbl. xSv%", get: p => p.xsv_pct, cell: p => sv(p.xsv_pct), tip: "xsvp" },
  { k: "gsax", label: "GSAx", get: p => p.gsax, cell: p => <b className="font-semibold"><Signed v={p.gsax} /></b>, tip: "gsax" },
  { k: "gsax_pace", label: "GSAx pace", get: p => pace(p.gsax, p.gp), cell: p => <Signed v={pace(p.gsax, p.gp)} />, tip: "gsaxpace" },
];

const FIRST = 15;

/** One ranked list with an ahead/behind switch: the same rows, sorted from
 *  either end. */
function Ranked<R>({ title, rows, cols, by, labels, csv, rowKey, children }: {
  title: string; rows: R[]; cols: Column<R>[]; by: string; labels: [string, string]; csv: string; rowKey: (r: R) => string | number; children: React.ReactNode;
}) {
  const [end, setEnd] = React.useState<"hi" | "lo">("hi");
  const [all, setAll] = React.useState(false);
  return (
    <Section title={title} aside={<Segmented label={title} value={end} onChange={v => { setEnd(v); setAll(false); }} options={[["hi", labels[0]], ["lo", labels[1]]]} />}>
      <SortTable key={end} rows={rows} cols={cols} initial={{ sort: by, asc: end === "lo" }} rowKey={rowKey} limit={all ? undefined : FIRST} csv={csv} />
      {!all && rows.length > FIRST && <Button variant="secondary" size="sm" className="mt-3" onClick={() => setAll(true)}>Show all {rows.length}</Button>}
      <Note className="mt-2 text-xs">{children}</Note>
    </Section>
  );
}

export function RegressionView({ season, data }: { season: number; data: Record<Phase, RegPhase> }) {
  const hasPlayoffs = data.playoff.teams.some(t => t.gp > 0);
  const [phase, setPhase] = React.useState<Phase>("regular");
  const d = data[phase];
  // Start at half the most games anyone has played: enough to cut the
  // call-ups, few enough to keep most of the league.
  const most = Math.max(1, ...d.skaters.map(p => p.gp));
  const gpOpts = [1, 3, 5, 10, 20, 40].filter(m => m <= most);
  const [minGp, setMinGp] = React.useState(() => gpOpts.filter(m => m <= most / 2).pop() ?? 1);

  const sk = React.useMemo(() => d.skaters.filter(p => p.gp >= minGp), [d, minGp]);
  const shooters = React.useMemo(() => sk.filter(p => p.att > 0), [sk]);
  const onIce = React.useMemo(() => sk.filter(p => p.xgf5 + p.xga5 > 0), [sk]);
  const gk = React.useMemo(() => d.goalies.filter(p => p.gp >= Math.min(minGp, 5)), [d, minGp]);
  const teams = React.useMemo(() => d.teams.filter(t => t.gp > 0), [d]);
  const tc = React.useMemo(() => teamCols(season), [season]);
  const shc = React.useMemo(() => shooterCols(season), [season]);
  const oic = React.useMemo(() => onIceCols(season), [season]);
  const gkc = React.useMemo(() => goalieCols(season), [season]);
  const csv = (k: string) => `regression-${k}-${season}-${phase}`;

  return (
    <>
      <div className="mb-6 flex flex-wrap items-end gap-3">
        {hasPlayoffs && <Segmented label="Season phase" value={phase} onChange={setPhase} options={[["regular", "Regular season"], ["playoff", "Playoffs"]]} />}
        <SelectField label="Min. games" value={minGp} onChange={v => setMinGp(+v)} options={gpOpts} />
      </div>

      <div className="space-y-10">
        <Ranked title="Teams" rows={teams} cols={tc} by="gap" labels={["Results ahead of play", "Results behind play"]} csv={csv("teams")} rowKey={t => t.team}>
          Gap is goal share minus xG share, in percentage points, all situations. A team well ahead of its chances is usually leaning on hot shooting or goaltending (the last two columns), and those are the parts that fade.
        </Ranked>
        <Ranked title="Shooters" rows={shooters} cols={shc} by="gax" labels={["Running hot", "Due for goals"]} csv={csv("shooters")} rowKey={p => p.id}>
          GAx is goals minus the expected goals of his own shots. The best finishers sit a little above zero year after year, but most big gaps shrink. Paces are per 82 games.
        </Ranked>
        <Ranked title="On-ice results, 5v5" rows={onIce} cols={oic} by="gap" labels={["Ahead of play", "Behind play"]} csv={csv("on-ice")} rowKey={p => p.id}>
          His team&apos;s 5-on-5 goal share with him on the ice, against its xG share. A skater whose goal share runs far ahead has usually had hot shooting or goaltending behind him; one far behind has usually had the opposite.
        </Ranked>
        <Ranked title="Goalies" rows={gk} cols={gkc} by="gsax" labels={["Stealing goals", "Leaking goals"]} csv={csv("goalies")} rowKey={p => p.id}>
          GSAx is how many goals he saved beyond an average goalie on the same shots. Goaltending is the noisiest thing in hockey over a few weeks: a season&apos;s worth of shots is needed before it says much.
        </Ranked>
      </div>
    </>
  );
}
