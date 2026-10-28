"use client";

import * as React from "react";
import Link from "next/link";
import { f1, pct, share, sv } from "@/lib/format";
import { clears, gaxCi, gsaxCi, onIceCi } from "@/lib/noise";
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

/** A goals gap in bold and colour when it is bigger than chance alone
 *  usually makes it (lib/noise.ts), muted when it isn't. */
const Noisy = ({ v, ci }: { v: number; ci: number }) =>
  clears(v, ci) ? <b className="font-semibold"><Signed v={v} /></b> : <span className="text-muted-foreground">{(v > 0 ? "+" : "") + v.toFixed(1)}</span>;
/** The 95% interval of the gap to its left. */
const ciCol = <R,>(ci: (r: R) => number): Column<R> =>
  ({ k: "ci", label: "±", get: ci, cell: r => <span className="text-muted-foreground">±{ci(r).toFixed(1)}</span>, tip: "ci95" });

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
  { k: "gax", label: "GAx", get: p => p.gax, cell: p => <Noisy v={p.gax} ci={gaxCi(p.ixg, p.att)} />, tip: "gax" },
  ciCol(p => gaxCi(p.ixg, p.att)),
  { k: "shp", label: "Sh%", get: p => (p.sog ? p.g / p.sog : null), cell: p => pct(p.sog ? p.g / p.sog : null), tip: "shp" },
  { k: "gpace", label: "Goal pace", get: p => pace(p.g, p.gp), cell: p => f1(pace(p.g, p.gp)), tip: "gpace" },
  { k: "xpace", label: "xG pace", get: p => pace(p.ixg, p.gp), cell: p => f1(pace(p.ixg, p.gp)), tip: "xpace" },
];

/** On-ice goal differential minus xG differential, in goals. */
const onIceGap = (p: RegSkater) => (p.gf5 - p.ga5) - (p.xgf5 - p.xga5);
const onIceCiOf = (p: RegSkater) => onIceCi(p.xgf5, p.xga5);
const onIceCols = (season: number): Column<RegSkater>[] => [
  nameCol("Skater"), teamCol(season),
  { k: "pos", label: "Pos", l: true, get: p => posLabel(p.pos), asc: true, cell: p => posLabel(p.pos) },
  { k: "gp", label: "GP", get: p => p.gp, tip: "gp" },
  { k: "toi5", label: "5v5 min", get: p => p.toi5 / 60, cell: p => (p.toi5 / 60).toFixed(0), tip: "toi5" },
  { k: "xgf", label: "xGF", get: p => p.xgf5, cell: p => f1(p.xgf5), tip: "xgf5" },
  { k: "gf", label: "GF", get: p => p.gf5, tip: "gf5" },
  { k: "xga", label: "xGA", get: p => p.xga5, cell: p => f1(p.xga5), asc: true, tip: "xga5" },
  { k: "ga", label: "GA", get: p => p.ga5, asc: true, tip: "ga5" },
  { k: "xgs5", label: "xG share", get: p => share(p.xgf5, p.xga5), cell: p => pct(share(p.xgf5, p.xga5)), tip: "xgs5" },
  { k: "gs5", label: "G share", get: p => share(p.gf5, p.ga5), cell: p => pct(share(p.gf5, p.ga5)), tip: "gs5" },
  { k: "gap", label: "Goal gap", get: onIceGap, cell: p => <Noisy v={onIceGap(p)} ci={onIceCiOf(p)} />, tip: "ggap5" },
  ciCol(onIceCiOf),
];

const goalieCols = (season: number): Column<RegGoalie>[] => [
  nameCol("Goalie"), teamCol(season),
  { k: "gp", label: "GP", get: p => p.gp, tip: "gp" },
  { k: "sa", label: "Shots", get: p => p.sa, tip: "sa" },
  { k: "ga", label: "GA", get: p => p.ga, asc: true, tip: "gaG" },
  { k: "xga", label: "xGA", get: p => p.xga, cell: p => f1(p.xga), tip: "xgaG" },
  { k: "sv_pct", label: "Unbl. Sv%", get: p => p.sv_pct, cell: p => sv(p.sv_pct), tip: "svp" },
  { k: "xsv_pct", label: "Unbl. xSv%", get: p => p.xsv_pct, cell: p => sv(p.xsv_pct), tip: "xsvp" },
  { k: "gsax", label: "GSAx", get: p => p.gsax, cell: p => <Noisy v={p.gsax} ci={gsaxCi(p.xga, p.sa)} />, tip: "gsax" },
  ciCol(p => gsaxCi(p.xga, p.sa)),
];

const FIRST = 15;

/** The sample size a list is filtered on, with the cut-offs on offer. */
interface Floor<R> { label: string; get: (r: R) => number; steps: number[]; start: (most: number) => number }
// Lists open at half the most anyone has: enough to cut the call-ups and
// the one-goal hot streaks, few enough to keep most of the league.
const half = (most: number) => most / 2;
const byGames = <R extends { gp: number }>(start: (most: number) => number): Floor<R> =>
  ({ label: "Min. games", get: r => r.gp, steps: [1, 3, 5, 10, 20, 40], start });
const byMinutes: Floor<RegSkater> =
  ({ label: "Min. 5v5 minutes", get: p => p.toi5 / 60, steps: [10, 25, 50, 100, 200, 400, 800], start: half });
const byShots: Floor<RegGoalie> =
  ({ label: "Min. shots faced", get: p => p.sa, steps: [25, 50, 100, 200, 400, 800, 1500], start: half });

/** One ranked list with an ahead/behind switch: the same rows, sorted from
 *  either end, with its own sample-size floor. */
function Ranked<R>({ title, rows: allRows, cols, by, labels, csv, rowKey, floor, children }: {
  title: string; rows: R[]; cols: Column<R>[]; by: string; labels: [string, string]; csv: string; rowKey: (r: R) => string | number;
  floor: Floor<R>; children: React.ReactNode;
}) {
  const [end, setEnd] = React.useState<"hi" | "lo">("hi");
  const [all, setAll] = React.useState(false);
  const most = Math.max(1, ...allRows.map(floor.get));
  const opts = floor.steps.filter((m, i) => i === 0 || m <= most);
  const [min, setMin] = React.useState(() => opts.filter(m => m <= floor.start(most)).pop() ?? opts[0]);
  const rows = React.useMemo(() => allRows.filter(r => floor.get(r) >= min), [allRows, floor, min]);
  return (
    <Section title={title} aside={
      <div className="flex flex-wrap items-end gap-3">
        <SelectField label={floor.label} value={min} onChange={v => { setMin(+v); setAll(false); }} options={opts} />
        <Segmented label={title} value={end} onChange={v => { setEnd(v); setAll(false); }} options={[["hi", labels[0]], ["lo", labels[1]]]} />
      </div>
    }>
      <SortTable key={end} rows={rows} cols={cols} initial={{ sort: by, asc: end === "lo" }} rowKey={rowKey} limit={all ? undefined : FIRST} csv={csv} />
      {!all && rows.length > FIRST && <Button variant="secondary" size="sm" className="mt-3" onClick={() => setAll(true)}>Show all {rows.length}</Button>}
      <Note className="mt-2 text-xs">{children}</Note>
    </Section>
  );
}

const teamFloor = byGames<RegTeam>(() => 1), shooterFloor = byGames<RegSkater>(half);

export function RegressionView({ season, data }: { season: number; data: Record<Phase, RegPhase> }) {
  const hasPlayoffs = data.playoff.teams.some(t => t.gp > 0);
  const [phase, setPhase] = React.useState<Phase>("regular");
  const d = data[phase];
  const shooters = React.useMemo(() => d.skaters.filter(p => p.att > 0), [d]);
  const onIce = React.useMemo(() => d.skaters.filter(p => p.xgf5 + p.xga5 > 0), [d]);
  const teams = React.useMemo(() => d.teams.filter(t => t.gp > 0), [d]);
  const tc = React.useMemo(() => teamCols(season), [season]);
  const shc = React.useMemo(() => shooterCols(season), [season]);
  const oic = React.useMemo(() => onIceCols(season), [season]);
  const gkc = React.useMemo(() => goalieCols(season), [season]);
  const csv = (k: string) => `regression-${k}-${season}-${phase}`;

  return (
    <>
      {hasPlayoffs && (
        <div className="mb-6">
          <Segmented label="Season phase" value={phase} onChange={setPhase} options={[["regular", "Regular season"], ["playoff", "Playoffs"]]} />
        </div>
      )}

      <div className="space-y-10">
        <Ranked key={`Teams-${phase}`} title="Teams" floor={teamFloor} rows={teams} cols={tc} by="gap" labels={["Results ahead of play", "Results behind play"]} csv={csv("teams")} rowKey={t => t.team}>
          Gap is goal share minus xG share, in percentage points, all situations. A team well ahead of its chances is usually leaning on hot shooting or goaltending (the last two columns), and those are the parts that fade.
        </Ranked>
        <Ranked key={`Shooters-${phase}`} title="Shooters" floor={shooterFloor} rows={shooters} cols={shc} by="gax" labels={["Running hot", "Due for goals"]} csv={csv("shooters")} rowKey={p => p.id}>
          GAx is goals minus the expected goals of his own shots. The best finishers sit a little above zero year after year, but most big gaps shrink. Paces are per 82 games. ± is the 95% range chance alone produces on his shots; a muted GAx sits inside it.
        </Ranked>
        <Ranked key={`On-ice results-${phase}`} title="On-ice results, 5v5" floor={byMinutes} rows={onIce} cols={oic} by="gap" labels={["Ahead of play", "Behind play"]} csv={csv("on-ice")} rowKey={p => p.id}>
          Goal gap is his 5-on-5 on-ice goal differential minus his xG differential, in goals, so it grows with ice time the way a real edge does. A skater far ahead has usually had hot shooting or goaltending behind him; one far behind has usually had the opposite. ± is the 95% range bounces alone produce in that much play; a muted gap sits inside it.
        </Ranked>
        <Ranked key={`Goalies-${phase}`} title="Goalies" floor={byShots} rows={d.goalies} cols={gkc} by="gsax" labels={["Stealing goals", "Leaking goals"]} csv={csv("goalies")} rowKey={p => p.id}>
          GSAx is how many goals he saved beyond an average goalie on the same shots. Goaltending is the noisiest thing in hockey over a few weeks: a season&apos;s worth of shots is needed before it says much. ± is the 95% range an average goalie&apos;s results span on the same shots; a muted GSAx sits inside it.
        </Ranked>
      </div>
    </>
  );
}
