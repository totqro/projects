"use client";

import * as React from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { f2, fmtDate, pct, share, toi } from "@/lib/format";
import type { GamePlayer } from "@/lib/types";
import { Signed, SortTable, type Column } from "@/components/tables/sortable";
import { Button } from "@/components/ui/button";

/** One game in a player's log, as the player page passes it. */
export interface LogRow {
  id: number; date: string; season: number; type: number; team: string; opp: string; home: boolean;
  gf: number; ga: number; end: string; line: GamePlayer;
}

const n = (v?: number) => v ?? 0;
const dateCol: Column<LogRow> = { k: "date", label: "Date", l: true, get: g => g.date + g.id,
  cell: g => <Link href={`/game/${g.id}`} className="hover:underline">{fmtDate(g.date)}{g.type === 3 ? " (playoffs)" : ""}</Link>, tip: "date" };
const oppCol: Column<LogRow> = { k: "opp", label: "Opp", l: true, get: g => g.opp, asc: true, cell: g => `${g.home ? "vs" : "@"} ${g.opp}`, tip: "opp" };
const resCol: Column<LogRow> = { k: "res", label: "Result", l: true, get: g => g.gf - g.ga, tip: "res",
  cell: g => <><b className={cn("font-semibold", g.gf > g.ga ? "text-good" : "text-bad")}>{g.gf > g.ga ? "W" : g.end === "REG" ? "L" : "OTL"}</b> {g.gf}&ndash;{g.ga}</> };

const SKATER: Column<LogRow>[] = [
  dateCol, oppCol, resCol,
  { k: "toi", label: "TOI", get: g => n(g.line.toi_all), cell: g => toi(g.line.toi_all), tip: "toitot" },
  { k: "g", label: "G", get: g => n(g.line.g), tip: "g" },
  { k: "a", label: "A", get: g => n(g.line.a), tip: "a" },
  { k: "p", label: "P", get: g => n(g.line.g) + n(g.line.a), cell: g => <b className="font-semibold">{n(g.line.g) + n(g.line.a)}</b>, tip: "p" },
  { k: "ixg", label: "ixG", get: g => n(g.line.ixg), cell: g => f2(n(g.line.ixg)), tip: "ixg" },
  { k: "att", label: "Att", get: g => n(g.line.att), tip: "att" },
  { k: "xgf", label: "xGF", get: g => n(g.line.xgf), cell: g => f2(n(g.line.xgf)), tip: "xgf" },
  { k: "gf", label: "GF", get: g => n(g.line.gf), tip: "gfOn" },
  { k: "xga", label: "xGA", get: g => n(g.line.xga), cell: g => f2(n(g.line.xga)), asc: true, tip: "xga" },
  { k: "ga", label: "GA", get: g => n(g.line.ga), asc: true, tip: "gaOn" },
  { k: "xgs", label: "xG share", get: g => share(n(g.line.xgf), n(g.line.xga)), cell: g => pct(share(n(g.line.xgf), n(g.line.xga)), 0), tip: "xgs" },
  { k: "gs", label: "G share", get: g => share(n(g.line.gf), n(g.line.ga)), cell: g => pct(share(n(g.line.gf), n(g.line.ga)), 0), tip: "gs" },
];
const GOALIE: Column<LogRow>[] = [
  dateCol, oppCol, resCol,
  { k: "toi", label: "TOI", get: g => n(g.line.toi_all), cell: g => toi(g.line.toi_all), tip: "toitot" },
  { k: "sa", label: "Shots", get: g => n(g.line.sa), tip: "sa" },
  { k: "ga", label: "GA", get: g => n(g.line.ga_), asc: true, tip: "gaG" },
  { k: "xga", label: "xGA", get: g => n(g.line.xga_), cell: g => f2(n(g.line.xga_)), tip: "xgaG" },
  { k: "gsax", label: "GSAx", get: g => n(g.line.xga_) - n(g.line.ga_), cell: g => <Signed v={n(g.line.xga_) - n(g.line.ga_)} d={2} />, tip: "gsax" },
];

/** Rows rendered before "Show all": a full season pre-rendered was most of
 *  a veteran's page. */
const FIRST = 20;

export function PlayerLog({ rows, goalie }: { rows: LogRow[]; goalie: boolean }) {
  const [all, setAll] = React.useState(rows.length <= FIRST);
  return (
    <>
      <SortTable rows={rows} cols={goalie ? GOALIE : SKATER} initial={{ sort: "date", asc: false }} rowKey={g => g.id} limit={all ? undefined : FIRST} />
      {!all && <Button variant="secondary" size="sm" className="mt-3" onClick={() => setAll(true)}>Show all {rows.length} games</Button>}
    </>
  );
}
