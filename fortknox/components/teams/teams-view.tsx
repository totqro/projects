"use client";

import * as React from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { TEAMS } from "@/lib/teams";
import { SelectField } from "@/components/site/field";
import { f1, f2, pct, per60, share, sv } from "@/lib/format";
import { groupTeams, LENSES, lensQuads, QCOL, xgStandings, type Grouping, type Quad, type StandingRow } from "@/lib/season";
import type { Phase } from "@/lib/types";
import { useLensChart } from "@/components/charts/lens";
import { Signed, SortTable, type Column } from "@/components/tables/sortable";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import * as ToggleGroupPrimitive from "@radix-ui/react-toggle-group";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Note, Section } from "@/components/site/section";
import { TeamLogo } from "@/components/site/team-logo";

type Row = StandingRow & { rk: string; cut?: boolean };
/** A row of the xG table: its real place in the same grouping, and for the
 *  wild-card view whether it is in a playoff spot now and on xG. */
type XRow = Row & { move: number | null; inNow?: boolean; inXg?: boolean };

const teamCol = <R extends { team: string }>(season: number): Column<R> => ({
  k: "team", label: "Team", l: true, pin: true, get: t => t.team, asc: true,
  cell: t => <Link href={`/team/${season}/${t.team}`} className="flex w-[4.25rem] items-center gap-2.5 font-medium hover:underline"><TeamLogo team={t.team} size={26} />{t.team}</Link>,
});

const cols = (season: number): Column<Row>[] => [
  { k: "std", label: "#", get: t => t.lg, asc: true, cell: t => <span className="text-muted-foreground">{t.rk}</span>, tip: "rank" },
  teamCol(season),
  { k: "gp", label: "GP", get: t => t.gp, tip: "gp" },
  { k: "w", label: "W", get: t => t.w, tip: "w" },
  { k: "l", label: "L", get: t => t.l, asc: true, tip: "l" },
  { k: "otl", label: "OTL", get: t => t.otl, tip: "otl" },
  { k: "pts", label: "PTS", get: t => t.pts, cell: t => <b className="font-semibold">{t.pts}</b>, tip: "pts" },
  { k: "ppct", label: "P%", get: t => t.ppct, cell: t => sv(t.ppct), tip: "ppct" },
  { k: "rw", label: "RW", get: t => t.rw, tip: "rw" },
  { k: "diff", label: "Diff", get: t => t.diff, cell: t => <Signed v={t.diff} d={0} />, tip: "diff" },
  { k: "xgf", label: "xGF", get: t => t.xgf, cell: t => f1(t.xgf), tip: "txgf" },
  { k: "gf", label: "GF", get: t => t.gf_x, tip: "tgf" },
  { k: "xga", label: "xGA", get: t => t.xga, cell: t => f1(t.xga), asc: true, tip: "txga" },
  { k: "ga", label: "GA", get: t => t.ga_x, asc: true, tip: "tga" },
  { k: "xgs", label: "xG share", get: t => share(t.xgf, t.xga), cell: t => pct(share(t.xgf, t.xga)), tip: "txgs" },
  { k: "gs", label: "G share", get: t => share(t.gf_x, t.ga_x), cell: t => pct(share(t.gf_x, t.ga_x)), tip: "tgs" },
  { k: "xgs5", label: "5v5 xG share", get: t => t["5v5"].xgf_pct, cell: t => <b className="font-semibold">{pct(t["5v5"].xgf_pct)}</b>, tip: "txgs5" },
  { k: "gs5", label: "5v5 G share", get: t => share(t["5v5"].gf, t["5v5"].ga), cell: t => pct(share(t["5v5"].gf, t["5v5"].ga)), tip: "tgs5" },
  { k: "xgf60", label: "5v5 xGF/60", get: t => t["5v5"].xgf60, cell: t => f2(t["5v5"].xgf60), tip: "txgf60" },
  { k: "gf60", label: "5v5 GF/60", get: t => per60(t["5v5"].gf, t["5v5"].toi), cell: t => f2(per60(t["5v5"].gf, t["5v5"].toi)), tip: "tgf60" },
  { k: "xga60", label: "5v5 xGA/60", get: t => t["5v5"].xga60, cell: t => f2(t["5v5"].xga60), asc: true, tip: "txga60" },
  { k: "ga60", label: "5v5 GA/60", get: t => per60(t["5v5"].ga, t["5v5"].toi), cell: t => f2(per60(t["5v5"].ga, t["5v5"].toi)), asc: true, tip: "tga60" },
  { k: "pp60", label: "PP xGF/60", get: t => t.pp.xgf60, cell: t => f2(t.pp.xgf60), tip: "pp60" },
  { k: "ppg60", label: "PP GF/60", get: t => per60(t.pp.gf, t.pp.toi), cell: t => f2(per60(t.pp.gf, t.pp.toi)), tip: "ppg60" },
  { k: "pk60", label: "PK xGA/60", get: t => t.pk.xga60, cell: t => f2(t.pk.xga60), asc: true, tip: "pk60" },
  { k: "pkg60", label: "PK GA/60", get: t => per60(t.pk.ga, t.pk.toi), cell: t => f2(per60(t.pk.ga, t.pk.toi)), asc: true, tip: "pkg60" },
  { k: "gax", label: "GAx", get: t => t.gax, cell: t => <Signed v={t.gax} />, tip: "tgax" },
  { k: "gsax", label: "GSAx", get: t => t.gsax, cell: t => <Signed v={t.gsax} />, tip: "tgsax" },
];

/** The standings columns a screen narrower than a computer's shows until the
 *  table is expanded; a computer always shows them all. */
const CORE = new Set(["std", "team", "gp", "w", "l", "otl", "pts", "ppct", "xgs5"]);
/** Core columns that also wait for the expand on a phone, so 5v5 xG share fits. */
const WIDE_ONLY = new Set(["w", "l", "otl"]);

/** A one-of-several picker. `tabs` draws it like the masthead's sections:
 *  plain text with the current one underlined in cyan (.slot-tabs). */
export function Segmented<T extends string>({ value, onChange, options, label, tabs }: {
  value: T; onChange: (v: T) => void; options: [T, string][]; label: string; tabs?: boolean;
}) {
  if (tabs) return (
    <ToggleGroupPrimitive.Root type="single" value={value} onValueChange={v => v && onChange(v as T)} aria-label={label}
      className="slot-tabs flex flex-wrap gap-1">
      {options.map(([k, l]) => (
        <ToggleGroupPrimitive.Item key={k} value={k}
          className="cursor-pointer px-2.5 py-2 text-sm font-medium text-muted-foreground transition-[color,box-shadow] hover:text-foreground">
          {l}
        </ToggleGroupPrimitive.Item>
      ))}
    </ToggleGroupPrimitive.Root>
  );
  return (
    <ToggleGroup type="single" value={value} onValueChange={v => v && onChange(v as T)} aria-label={label} className="flex-wrap">
      {options.map(([k, l]) => <ToggleGroupItem key={k} value={k}>{l}</ToggleGroupItem>)}
    </ToggleGroup>
  );
}


const xcols = (season: number, wildcard: boolean): Column<XRow>[] => [
  { k: "std", label: "#", get: t => t.lg, asc: true, cell: t => <span className="text-muted-foreground">{t.rk}</span>, tip: "xrank" },
  teamCol(season),
  { k: "gp", label: "GP", get: t => t.gp, tip: "gp" },
  { k: "xw", label: "xW", get: t => t.xw, tip: "xw" },
  { k: "xl", label: "xL", get: t => t.xl, asc: true, tip: "xl" },
  { k: "xotl", label: "xOTL", get: t => t.xotl, tip: "xotl" },
  { k: "xpts", label: "xPts", get: t => t.xpts, cell: t => <b className="font-semibold">{t.xpts}</b>, tip: "xpts" },
  { k: "pts", label: "PTS", get: t => t.pts, tip: "pts" },
  { k: "dpts", label: "PTS − xPts", get: t => (t.xpts == null ? null : t.pts - t.xpts), cell: t => <Signed v={t.xpts == null ? null : t.pts - t.xpts} d={0} />, tip: "dpts" },
  { k: "xppct", label: "xP%", get: t => t.xppct, cell: t => sv(t.xppct), tip: "xppct" },
  { k: "ppct", label: "P%", get: t => t.ppct, cell: t => sv(t.ppct), tip: "ppct" },
  wildcard
    ? { k: "now", label: "Now", l: true, get: t => (t.inNow ? 1 : 0), tip: "inout",
        cell: t => <span className={cn(t.inNow !== t.inXg && (t.inXg ? "text-good" : "text-bad"), "whitespace-nowrap")}>{t.inNow ? "In" : "Out"}</span> }
    : { k: "move", label: "vs. real", get: t => t.move, tip: "move",
        cell: t => !t.move ? <span className="text-muted-foreground">–</span>
          : <span className={t.move > 0 ? "text-good" : "text-bad"}>{t.move > 0 ? "↑" : "↓"}{Math.abs(t.move)}</span> },
  { k: "xgs", label: "xG share", get: t => share(t.xgf, t.xga), cell: t => pct(share(t.xgf, t.xga)), tip: "txgs" },
];

/** The real groups and the xG groups side by side: each xG row learns where
 *  the team really stands in the same grouping. */
function xgGroups(rows: StandingRow[], group: Grouping) {
  const real = groupTeams(rows, group), xg = groupTeams(xgStandings(rows), group);
  const pos = new Map<string, number>();
  for (const g of real) g.rows.forEach((t, i) => pos.set(`${g.title}|${t.team}`, i));
  // Playoff spots: the top three in each division and two wild cards.
  const playoff = (gs: typeof real) => new Set(gs.flatMap(g => g.title?.endsWith("wild card") ? g.rows.slice(0, 2) : g.rows).map(t => t.team));
  const inNow = group === "wildcard" ? playoff(real) : null, inXg = group === "wildcard" ? playoff(xg) : null;
  return xg.map(g => ({
    title: g.title,
    rows: g.rows.map((t, i): XRow => {
      const was = pos.get(`${g.title}|${t.team}`);
      return { ...t, move: was == null ? null : was - i, inNow: inNow?.has(t.team), inXg: inXg?.has(t.team) };
    }),
  }));
}

/** Better quadrants sort first: the x axis is the process number, so being
 *  on its good side counts for more than the y axis. */
const QRANK: Record<Quad, number> = { hh: 3, hl: 2, lh: 1, ll: 0 };
const LENS_KEYS = Object.keys(LENSES);

type SumRow = StandingRow & { rk: string; q: Record<string, Quad | undefined> };

const sumCols = (season: number): Column<SumRow>[] => [
  teamCol(season),
  { k: "rec", label: "Record", l: true, get: t => t.pts, cell: t => <span className="whitespace-nowrap">{t.w}-{t.l}-{t.otl}</span>, tip: "pts" },
  { k: "xgs5", label: "5v5 xG share", get: t => t["5v5"].xgf_pct, cell: t => pct(t["5v5"].xgf_pct), tip: "txgs5" },
  ...LENS_KEYS.map((k): Column<SumRow> => ({
    k, label: LENSES[k].name, l: true, tip: "sumq",
    get: t => (t.q[k] ? QRANK[t.q[k]!] : null),
    cell: t => {
      const q = t.q[k];
      if (!q) return "–";
      return (
        <span className="whitespace-nowrap">
          <i className="mr-1.5 inline-block size-2 rounded-full align-[1px]" style={{ background: QCOL[q] }} />{LENSES[k].q[q][2]}
        </span>
      );
    },
  })),
];

const SUMMARY = "summary";

/** What the charts can pick out: a conference or a division. */
const FOCUS: [string, string][] = [
  ["all", "All teams"], ["c:East", "Eastern Conference"], ["c:West", "Western Conference"],
  ["d:Atlantic", "Atlantic Division"], ["d:Metropolitan", "Metropolitan Division"], ["d:Central", "Central Division"], ["d:Pacific", "Pacific Division"],
];
const focusSet = (f: string) => {
  if (f === "all") return null;
  const [kind, name] = f.split(":");
  return new Set(Object.entries(TEAMS).filter(([, t]) => t[kind === "c" ? 1 : 2] === name).map(([ab]) => ab));
};

export function TeamsView({ season, regular, playoff }: { season: number; regular: StandingRow[]; playoff: StandingRow[] }) {
  const [phase, setPhase] = React.useState<Phase>("regular");
  const [group, setGroup] = React.useState<Grouping>("league");
  const [sumGroup, setSumGroup] = React.useState<Grouping>("league");
  const [table, setTable] = React.useState<"real" | "xg">("real");
  const [expanded, setExpanded] = React.useState(false);
  const [lens, setLens] = React.useState("drive");
  const [focus, setFocus] = React.useState("all");
  const focused = React.useMemo(() => focusSet(focus), [focus]);
  const rows = phase === "playoff" ? playoff : regular;
  const summary = lens === SUMMARY;
  const chart = useLensChart({ rows, lens: summary ? "drive" : lens, season, focus: focused });
  // Points only exist in the regular season, so the xG table does too.
  const xg = table === "xg" && phase === "regular" && rows.some(t => t.xpts != null);
  const g = phase === "playoff" ? "league" : group;
  const groups = groupTeams(rows, g);
  const xGroups = React.useMemo(() => xgGroups(rows, g), [rows, g]);
  const all = React.useMemo(() => cols(season), [season]);
  const columns = React.useMemo(() => all.map(c => (!CORE.has(c.k) ? { ...c, more: true } : !expanded && WIDE_ONLY.has(c.k) ? { ...c, wide: true } : c)), [all, expanded]);
  const xColumns = React.useMemo(() => xcols(season, g === "wildcard"), [season, g]);
  const sumRows = React.useMemo(() => {
    const qs = Object.fromEntries(LENS_KEYS.map(k => [k, lensQuads(rows, k)]));
    const withQ = rows.map(t => ({ ...t, q: Object.fromEntries(LENS_KEYS.map(k => [k, qs[k].get(t.team)])) }));
    return groupTeams(withQ as StandingRow[], phase === "playoff" ? "league" : sumGroup) as unknown as { title: string | null; rows: SumRow[] }[];
  }, [rows, sumGroup, phase]);
  const sumColumns = React.useMemo(() => sumCols(season), [season]);
  const csvName = (prefix: string, title: string | null) => `${prefix}-${season}${title ? "-" + title.toLowerCase().replace(/[^a-z]+/g, "-") : ""}`;
  return (
    <>
      {playoff.length > 0 && (
        <div className="mb-5">
          <Segmented label="Season phase" value={phase} onChange={setPhase} options={[["regular", "Regular season"], ["playoff", "Playoffs"]]} />
        </div>
      )}

      <Card className="mb-8">
        <CardHeader className="gap-3 pb-3">
          <CardTitle>xG performance</CardTitle>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <Segmented tabs label="Chart" value={lens} onChange={setLens}
              options={[...LENS_KEYS.map(k => [k, LENSES[k].name] as [string, string]), [SUMMARY, "Summary"]]} />
            {!summary && <SelectField label="Highlight" value={focus} onChange={setFocus} options={FOCUS} align="end" />}
          </div>
          <p className="max-w-3xl text-[13px] leading-relaxed text-muted-foreground">
            {summary
              ? "Where every team lands on each of the four charts, in one table. Sort by any column, or narrow it to a division to compare rivals."
              : LENSES[lens].desc}
          </p>
        </CardHeader>
        {summary ? (
          <CardContent className="space-y-6">
            {phase === "regular" && (
              <Segmented tabs label="Summary grouping" value={sumGroup} onChange={setSumGroup}
                options={[["league", "All teams"], ["conference", "Conference"], ["division", "Division"]]} />
            )}
            {sumRows.map((s, i) => (
              <Section key={s.title ?? i} title={s.title ?? "All teams"}>
                <SortTable rows={s.rows} cols={sumColumns} initial={{ sort: "team", asc: true }}
                  csv={csvName("teams-summary", s.title)} rowKey={t => t.team} />
              </Section>
            ))}
          </CardContent>
        ) : (
          <CardContent className="grid gap-5 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
            <div>{chart.svg}</div>
            <div>
              {chart.callouts}
              <Note className="mt-3 text-xs">
                Top right is better. The dashed lines are the league average{lens === "luck" ? " (50%)" : ""}. + and − mean above or below it.
              </Note>
            </div>
          </CardContent>
        )}
      </Card>

      <div id="standings" className="mb-5 flex scroll-mt-20 flex-wrap items-center gap-x-6 gap-y-3">
        {phase === "regular" && (
          <>
            <Segmented label="Standings table" value={table} onChange={setTable} options={[["real", "Standings"], ["xg", "xG standings"]]} />
            <Segmented tabs label="Standings grouping" value={group} onChange={setGroup}
              options={[["league", "League"], ["conference", "Conference"], ["division", "Division"], ["wildcard", "Wild card"]]} />
          </>
        )}
      </div>
      {xg && (
        <Note className="mb-5 max-w-3xl text-[13px]">
          The standings if every game went to the team with more expected goals (empty-net shots left out). An xG win
          is worth 2 points. Losing on xG by 0.25 or less is a close loss (xOTL), worth 1 point like an overtime loss;
          losing by more is worth nothing.
          {g === "wildcard" && " Green and red in “Now” mark teams the shots would move into or out of a playoff spot."}
        </Note>
      )}
      <div className="space-y-6">
        {xg
          ? xGroups.map((x, i) => (
            <Section key={x.title ?? i} title={x.title ? `${x.title}, by xG` : "xG standings"}>
              <SortTable rows={x.rows} cols={xColumns} initial={{ sort: "std", asc: true }} naturalKey="std"
                csv={csvName("xg-standings", x.title)}
                rowKey={t => t.team} rowProps={t => ({ className: cn(t.cut && "cut") })} />
            </Section>
          ))
          : groups.map((x, i) => (
            <Section key={x.title ?? i} title={x.title ?? "Standings"} aside={i === 0 && (
              // Only below computer width, where the table starts compact.
              <button type="button" aria-expanded={expanded} onClick={() => setExpanded(e => !e)}
                className="rounded-md border border-border px-2.5 py-1 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground lg:hidden">
                {expanded ? "Fewer columns" : `Show all ${columns.length} columns`}
              </button>
            )}>
              <SortTable rows={x.rows} cols={columns} initial={{ sort: "std", asc: true }} naturalKey="std"
                csv={csvName("teams", x.title)} className={expanded ? "fk-all" : undefined}
                rowKey={t => t.team} rowProps={t => ({ className: cn(t.cut && "cut") })} />
            </Section>
          ))}
      </div>
    </>
  );
}
