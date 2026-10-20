"use client";

import Link from "next/link";
import { f2, pct, share, toi } from "@/lib/format";
import { posLabel } from "@/lib/teams";
import type { GamePlayer } from "@/lib/types";
import { Signed, SortTable, TipHead, type Column } from "@/components/tables/sortable";
import { Table, TableBody, TableCell, TableHeader, TableRow } from "@/components/ui/table";

const n = (v?: number) => v ?? 0;

const SKATER_COLS: Column<GamePlayer>[] = [
  { k: "name", label: "Skater", l: true, get: p => p.name, asc: true,
    cell: p => <><Link href={`/player/${p.id}`} className="hover:underline">{p.name}</Link> <span className="text-muted-foreground">{posLabel(p.pos)}</span></> },
  { k: "toi", label: "TOI", get: p => n(p.toi_all), cell: p => toi(p.toi_all), tip: "toitot" },
  { k: "toi5", label: "5v5", get: p => n(p.toi_5v5), cell: p => toi(p.toi_5v5), tip: "toi5" },
  { k: "g", label: "G", get: p => n(p.g), tip: "g" },
  { k: "a", label: "A", get: p => n(p.a), tip: "a" },
  { k: "p", label: "P", get: p => n(p.g) + n(p.a), tip: "p" },
  { k: "ixg", label: "ixG", get: p => n(p.ixg), cell: p => f2(n(p.ixg)), tip: "ixg" },
  { k: "att", label: "Att", get: p => n(p.att), tip: "att" },
  { k: "xgf", label: "xGF", get: p => n(p.xgf), cell: p => f2(n(p.xgf)), tip: "xgf" },
  { k: "xga", label: "xGA", get: p => n(p.xga), cell: p => f2(n(p.xga)), asc: true, tip: "xga" },
  { k: "xgs", label: "xG share", get: p => share(n(p.xgf), n(p.xga)), cell: p => pct(share(n(p.xgf), n(p.xga)), 0), tip: "xgs" },
  { k: "xgs5", label: "5v5 xG share", get: p => share(n(p.xgf5), n(p.xga5)), cell: p => pct(share(n(p.xgf5), n(p.xga5)), 0), tip: "xgs5" },
];

/** One team's skaters (sortable) and goalies in a single game. */
export function GameRoster({ players }: { players: GamePlayer[] }) {
  const sk = players.filter(p => p.pos !== "G" && (p.toi_all || p.att));
  const gk = players.filter(p => p.pos === "G" && (p.toi_all || p.sa));
  const cell = "whitespace-nowrap px-2.5 py-2 text-right";
  return (
    <div className="space-y-3">
      <SortTable rows={sk} cols={SKATER_COLS} initial={{ sort: "toi", asc: false }} rowKey={p => p.id} />
      <Table className="tabular text-[13px]">
        <TableHeader className="bg-transparent">
          <TableRow className="hover:bg-transparent">
            <TipHead className="text-left">Goalie</TipHead>
            <TipHead tip="toitot">TOI</TipHead><TipHead tip="sa">Shots</TipHead>
            <TipHead tip="gaG">GA</TipHead><TipHead tip="xgaG">xGA</TipHead><TipHead tip="gsax">GSAx</TipHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {gk.map(p => (
            <TableRow key={p.id}>
              <TableCell className="whitespace-nowrap px-2.5 py-2"><Link href={`/player/${p.id}`} className="hover:underline">{p.name}</Link></TableCell>
              <TableCell className={cell}>{toi(p.toi_all)}</TableCell>
              <TableCell className={cell}>{n(p.sa)}</TableCell>
              <TableCell className={cell}>{n(p.ga_)}</TableCell>
              <TableCell className={cell}>{f2(n(p.xga_))}</TableCell>
              <TableCell className={cell}><Signed v={n(p.xga_) - n(p.ga_)} d={2} /></TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
