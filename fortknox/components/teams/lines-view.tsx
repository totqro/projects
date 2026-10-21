"use client";

import * as React from "react";
import Link from "next/link";
import { f2, pct, per60, share, toiMin } from "@/lib/format";
import { posLabel } from "@/lib/teams";
import type { TeamUnits, UnitRow } from "@/lib/types";
import { SortTable, type Column } from "@/components/tables/sortable";
import { SelectField } from "@/components/site/field";
import { Note, Section } from "@/components/site/section";

// 5v5 forward lines, defence pairs and with-or-without-you, from lines.json
// (pipeline/nhl_sheets.py). Every number is 5v5 only.

interface Unit { key: string; ids: number[]; toi: number; xgf: number; xga: number; gf: number; ga: number; cf: number; ca: number }
const unit = ([ids, toi, xgf, xga, gf, ga, cf, ca]: UnitRow): Unit => ({ key: ids.join("-"), ids, toi, xgf, xga, gf, ga, cf, ca });
const minus = (a: Unit, b: Unit): Unit =>
  ({ key: a.key, ids: a.ids, toi: a.toi - b.toi, xgf: a.xgf - b.xgf, xga: a.xga - b.xga, gf: a.gf - b.gf, ga: a.ga - b.ga, cf: a.cf - b.cf, ca: a.ca - b.ca });

/** Last name, or the whole name when there's only one word. */
const last = (n: string) => n.split(" ").slice(1).join(" ") || n;

function unitCols(names: TeamUnits["players"], label: string): Column<Unit>[] {
  const nm = (id: number) => names[id]?.[0] ?? String(id);
  return [
    { k: "who", label, l: true, pin: true, get: u => u.ids.map(i => last(nm(i))).join(" – "), asc: true,
      cell: u => <span className="whitespace-nowrap">{u.ids.map((id, i) => (
        <React.Fragment key={id}>{i > 0 && <span className="text-muted-foreground"> – </span>}<Link href={`/player/${id}`} className="hover:underline">{last(nm(id))}</Link></React.Fragment>
      ))}</span> },
    { k: "toi", label: "TOI", unit: "sec", get: u => u.toi, cell: u => toiMin(u.toi), tip: "Minutes together at 5-on-5." },
    { k: "xgf", label: "xGF", get: u => u.xgf, cell: u => f2(u.xgf), tip: "Expected goals for while this group was on the ice together." },
    { k: "xga", label: "xGA", get: u => u.xga, cell: u => f2(u.xga), asc: true, tip: "Expected goals against while this group was on the ice together." },
    { k: "xgs", label: "xG%", get: u => share(u.xgf, u.xga), cell: u => <b className="font-semibold">{pct(share(u.xgf, u.xga))}</b>, tip: "xG share together: xGF / (xGF + xGA)." },
    { k: "gf", label: "GF", get: u => u.gf, tip: "Goals for together." },
    { k: "ga", label: "GA", get: u => u.ga, asc: true, tip: "Goals against together." },
    { k: "gs", label: "G%", get: u => share(u.gf, u.ga), cell: u => pct(share(u.gf, u.ga)), tip: "Goal share together. Over a few hundred minutes it says more about luck than xG% does." },
    { k: "xgf60", label: "xGF/60", get: u => per60(u.xgf, u.toi), cell: u => f2(per60(u.xgf, u.toi)), tip: "Expected goals for per 60 minutes together." },
    { k: "xga60", label: "xGA/60", get: u => per60(u.xga, u.toi), cell: u => f2(per60(u.xga, u.toi)), asc: true, tip: "Expected goals against per 60 minutes together. Lower is better." },
    { k: "cs", label: "Att%", get: u => share(u.cf, u.ca), cell: u => pct(share(u.cf, u.ca)), tip: "Share of shot attempts (Corsi) together, blocked and missed shots included." },
  ];
}

const MINUTES = [0, 10, 25, 50, 100, 200, 400];

/** Forward lines and defence pairs, with a minimum-minutes filter. */
export function LinesTables({ units, csvName }: { units: TeamUnits; csvName: string }) {
  const fwd = React.useMemo(() => units.fwd.map(unit), [units]);
  const def = React.useMemo(() => units.def.map(unit), [units]);
  // Start with the filter that leaves a readable list: about a dozen lines.
  const [min, setMin] = React.useState(() => [...MINUTES].reverse().find(m => fwd.filter(u => u.toi >= m * 60).length >= 8) ?? 0);
  const fc = React.useMemo(() => unitCols(units.players, "Forward line"), [units]);
  const dc = React.useMemo(() => unitCols(units.players, "Defence pair"), [units]);
  const keep = (u: Unit) => u.toi >= min * 60;
  return (
    <div className="space-y-6">
      <Section title="Forward lines" aside={
        <SelectField label="Min. minutes together" value={min} onChange={v => setMin(+v)} className="flex-row items-center gap-2" options={MINUTES} />
      }>
        <SortTable rows={fwd.filter(keep)} cols={fc} initial={{ sort: "toi", asc: false }} rowKey={u => u.key} csv={`${csvName}-forward-lines`} />
      </Section>
      <Section title="Defence pairs">
        <SortTable rows={def.filter(keep)} cols={dc} initial={{ sort: "toi", asc: false }} rowKey={u => u.key} csv={`${csvName}-defence-pairs`} />
      </Section>
      <Note>5-on-5 only. A line is the three forwards on the ice together, whoever the defence was.</Note>
    </div>
  );
}

interface WowyRow { id: number; name: string; pos: string; with: Unit; me: Unit; mate: Unit }

/** One player against each teammate: together, him without the teammate,
 *  the teammate without him. */
export function WowyTable({ units, playerId, minSecs = 60, csvName }: { units: TeamUnits; playerId: number; minSecs?: number; csvName: string }) {
  const rows = React.useMemo(() => {
    const solo = new Map(units.solo.map(r => [r[0][0], unit(r)]));
    const me = solo.get(playerId);
    if (!me) return [];
    return units.pairs.filter(r => r[0].includes(playerId) && r[1] >= minSecs).flatMap((r): WowyRow[] => {
      const id = r[0][0] === playerId ? r[0][1] : r[0][0], w = unit(r), mate = solo.get(id);
      if (!mate) return [];
      const [name, pos] = units.players[id] ?? [String(id), ""];
      return [{ id, name, pos, with: w, me: minus(me, w), mate: minus(mate, w) }];
    });
  }, [units, playerId, minSecs]);
  const myName = last(units.players[playerId]?.[0] ?? "him");
  const cols = React.useMemo((): Column<WowyRow>[] => [
    { k: "name", label: "Teammate", l: true, pin: true, get: r => r.name, asc: true, cell: r => <Link href={`/player/${r.id}`} className="hover:underline">{r.name}</Link> },
    { k: "pos", label: "Pos", l: true, get: r => posLabel(r.pos), asc: true },
    { k: "toi", label: "Together", unit: "sec", get: r => r.with.toi, cell: r => toiMin(r.with.toi), tip: "Minutes on the ice together at 5-on-5." },
    { k: "xgs", label: "xG% together", get: r => share(r.with.xgf, r.with.xga), cell: r => <b className="font-semibold">{pct(share(r.with.xgf, r.with.xga))}</b>, tip: "xG share with both of them on the ice." },
    { k: "gs", label: "G% together", get: r => share(r.with.gf, r.with.ga), cell: r => pct(share(r.with.gf, r.with.ga)), tip: "Goal share with both on the ice." },
    { k: "metoi", label: `${myName} without`, unit: "sec", get: r => r.me.toi, cell: r => toiMin(r.me.toi), tip: `Minutes ${myName} played without this teammate.` },
    { k: "mexgs", label: "xG%", get: r => share(r.me.xgf, r.me.xga), cell: r => pct(share(r.me.xgf, r.me.xga)), tip: `xG share with ${myName} on the ice and this teammate off it.` },
    { k: "matetoi", label: "Teammate without", unit: "sec", get: r => r.mate.toi, cell: r => toiMin(r.mate.toi), tip: `Minutes the teammate played without ${myName}.` },
    { k: "matexgs", label: "xG%", get: r => share(r.mate.xgf, r.mate.xga), cell: r => pct(share(r.mate.xgf, r.mate.xga)), tip: `xG share with the teammate on the ice and ${myName} off it.` },
  ], [myName]);
  if (!rows.length) return <Note>No 5-on-5 time with teammates yet.</Note>;
  return <SortTable rows={rows} cols={cols} initial={{ sort: "toi", asc: false }} rowKey={r => r.id} csv={`${csvName}-wowy`} />;
}

/** WOWY with a player picker, for the team page. */
export function TeamWowy({ units, csvName }: { units: TeamUnits; csvName: string }) {
  const skaters = React.useMemo(() => units.solo.map(unit).sort((a, b) => b.toi - a.toi)
    .map(u => [String(u.ids[0]), units.players[u.ids[0]]?.[0] ?? String(u.ids[0])] as [string, string]), [units]);
  const [who, setWho] = React.useState(skaters[0]?.[0] ?? "");
  if (!skaters.length) return null;
  return (
    <Section title="With or without you" aside={
      <SelectField label="Player" value={who} onChange={setWho} className="flex-row items-center gap-2" options={skaters} />
    }>
      <WowyTable units={units} playerId={+who} csvName={`${csvName}-${who}`} />
      <Note className="mt-3">5-on-5. How the team did with both players on the ice, and with each of them out there without the other. A player who lifts everyone he plays with shows a higher xG% together than his teammates manage without him.</Note>
    </Section>
  );
}
