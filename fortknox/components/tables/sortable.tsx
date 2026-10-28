"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { TIPS } from "@/lib/teams";
import { Table, TableBody, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

export type SortValue = number | string | null | undefined;

export interface Column<R> {
  k: string;
  label: string;
  /** Sort key; columns without one aren't sortable. */
  get?: (r: R) => SortValue;
  cell?: (r: R, i: number) => React.ReactNode;
  /** Left-aligned (text) column. */
  l?: boolean;
  /** Sorts ascending on first click (lower is better). */
  asc?: boolean;
  /** Key into TIPS, shown on hover. */
  tip?: string;
  /** Stays in view while the table scrolls sideways (the name or team). */
  pin?: boolean;
  /** Unit of the raw sort value, named in the CSV header ("sec"). */
  unit?: string;
  /** Hidden on phone-width screens (.fk-wide in globals.css). */
  wide?: boolean;
  /** Hidden below computer width until the table is expanded (.fk-more). */
  more?: boolean;
  className?: string;
}

export interface SortState { sort: string; asc: boolean }

export function sortRows<R>(rows: R[], cols: Column<R>[], st: SortState) {
  const col = cols.find(c => c.k === st.sort && c.get) ?? cols.find(c => c.get);
  if (!col?.get) return rows;
  const g = col.get;
  return rows.slice().sort((a, b) => {
    const x = g(a), y = g(b);
    if (x == null && y == null) return 0;
    if (x == null) return 1;
    if (y == null) return -1;
    const c = typeof x === "string" ? x.localeCompare(String(y)) : (x as number) - (y as number);
    return st.asc ? c : -c;
  });
}

/** A column heading that explains itself on hover. */
export function TipHead({ tip, children, className, ...rest }: React.ThHTMLAttributes<HTMLTableCellElement> & { tip?: string }) {
  const text = tip ? TIPS[tip] ?? tip : null;
  const head = (
    <TableHead className={cn("h-9 whitespace-nowrap px-2.5 text-right text-xs font-medium normal-case tracking-normal", className)} {...rest}>
      {text ? <span className="cursor-help underline decoration-dotted decoration-border underline-offset-4">{children}</span> : children}
    </TableHead>
  );
  if (!text) return head;
  return (
    <Tooltip>
      <TooltipTrigger asChild>{head}</TooltipTrigger>
      <TooltipContent className="max-w-72 text-pretty leading-relaxed">{text}</TooltipContent>
    </Tooltip>
  );
}

interface Props<R> {
  rows: R[];
  cols: Column<R>[];
  initial: SortState;
  rowKey: (r: R) => string | number;
  rowProps?: (r: R) => React.HTMLAttributes<HTMLTableRowElement> & { "data-state"?: string };
  /** Sorting is skipped (rows kept in the given order) while this is the active key. */
  naturalKey?: string;
  limit?: number;
  className?: string;
  /** File name (no extension) for a "Download CSV" link under the table. */
  csv?: string;
  /** Column keys left out of the view; the CSV still has every column. */
  hide?: ReadonlySet<string>;
}

/** The sorted rows as CSV: every column with a sort value, raw numbers. */
function toCsv<R>(rows: R[], cols: Column<R>[]) {
  const out = cols.filter(c => c.get);
  const esc = (v: SortValue) => {
    if (v == null) return "";
    if (typeof v === "number") return Number.isInteger(v) ? String(v) : String(+v.toFixed(4));
    return /[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v;
  };
  return [out.map(c => esc(c.unit ? `${c.label} (${c.unit})` : c.label)).join(","),
    ...rows.map(r => out.map(c => esc(c.get!(r))).join(","))].join("\n");
}

function download(name: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: `${name}.csv` });
  a.click();
  URL.revokeObjectURL(url);
}

/** A table that re-sorts on any heading. The DS Table, with a sort state.
 *  Body rows are plain <tr>/<td> styled once by .fk-table (globals.css): a
 *  season table has thousands of cells, and per-cell utility classes made
 *  each static page several times larger. */
export function SortTable<R>({ rows, cols: all, initial, rowKey, rowProps, naturalKey, limit, className, csv, hide }: Props<R>) {
  const cols = React.useMemo(() => (hide ? all.filter(c => !hide.has(c.k)) : all), [all, hide]);
  const [st, setSt] = React.useState(initial);
  const sorted = React.useMemo(() => {
    if (naturalKey && st.sort === naturalKey) return st.asc ? rows : rows.slice().reverse();
    return sortRows(rows, all, st);
  }, [rows, all, st, naturalKey]);
  const shown = limit ? sorted.slice(0, limit) : sorted;
  const click = (c: Column<R>) => {
    if (!c.get && c.k !== naturalKey) return;
    setSt(s => (s.sort === c.k ? { sort: c.k, asc: !s.asc } : { sort: c.k, asc: c.asc === true }));
  };
  const table = (
    <Table className={cn("fk-table tabular text-[13px]", className)}>
      <TableHeader className="bg-transparent">
        <TableRow className="hover:bg-transparent">
          {cols.map(c => {
            const on = st.sort === c.k;
            const sortable = !!c.get || c.k === naturalKey;
            return (
              <TipHead key={c.k} tip={c.tip}
                aria-sort={on ? (st.asc ? "ascending" : "descending") : undefined}
                onClick={() => click(c)}
                className={cn(c.l && "text-left", c.pin && "pin", c.wide && "fk-wide", c.more && "fk-more", sortable && "cursor-pointer select-none hover:text-foreground", on && "text-foreground")}>
                {c.label}{on ? (st.asc ? " ▴" : " ▾") : ""}
              </TipHead>
            );
          })}
        </TableRow>
      </TableHeader>
      <TableBody>
        {shown.map((r, i) => (
          <tr key={rowKey(r)} {...rowProps?.(r)}>
            {cols.map(c => (
              <td key={c.k} className={cn(c.l && "l", c.pin && "pin", c.wide && "fk-wide", c.more && "fk-more", c.className) || undefined}>
                {c.cell ? c.cell(r, i) : String(c.get?.(r) ?? "\u2013")}
              </td>
            ))}
          </tr>
        ))}
      </TableBody>
    </Table>
  );
  if (!csv) return table;
  return (
    <>
      {table}
      <div className="mt-1.5 flex justify-end">
        <button type="button" onClick={() => download(csv, toCsv(sorted, all))}
          className="rounded px-1.5 py-0.5 text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline">
          Download CSV
        </button>
      </div>
    </>
  );
}

/** +1.2 in green, -0.4 in red. */
export function Signed({ v, d = 1 }: { v: number | null | undefined; d?: number }) {
  if (v == null) return <>{"–"}</>;
  return <span className={cn(v > 0 && "text-good", v < 0 && "text-bad")}>{(v > 0 ? "+" : "") + v.toFixed(d)}</span>;
}
