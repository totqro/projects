"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { ORD, toi } from "@/lib/format";
import { bestChances, lastName, pname, scoring } from "@/lib/game";
import { EVN, shotNoun, SIT } from "@/lib/teams";
import type { RawSheet, Sheet, Shot } from "@/lib/types";
import { unpack } from "@/lib/unpack";
import { RinkMarks, shotRadius } from "@/components/charts/rink";
import { Button } from "@/components/ui/button";
import { Block } from "@/components/site/section";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Switch } from "@/components/ui/switch";

// Picking a shot (from Best chances, Scoring or the rink itself) rings it on
// the rink, fades the rest and writes it out under the map.

interface Ctx { G: Sheet; sel: number | null; pick: (i: number, scroll?: boolean) => void; mapRef: React.RefObject<SVGSVGElement | null> }
const ShotCtx = React.createContext<Ctx | null>(null);
const useShots = () => React.useContext(ShotCtx)!;

export function ShotProvider({ raw, children }: { raw: RawSheet; children: React.ReactNode }) {
  const G = React.useMemo(() => unpack(raw), [raw]);
  const [sel, setSel] = React.useState<number | null>(null);
  const mapRef = React.useRef<SVGSVGElement>(null);
  const pick = React.useCallback((i: number, scroll = false) => {
    setSel(s => (s === i ? null : i));
    const svg = mapRef.current;
    if (scroll && svg) {
      const r = svg.getBoundingClientRect();
      if (r.top < 0 || r.bottom > innerHeight) svg.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, []);
  return <ShotCtx.Provider value={{ G, sel, pick, mapRef }}>{children}</ShotCtx.Provider>;
}

const sideClass = (G: Sheet, team: string) => (team === G.home.abbrev ? "text-home" : "text-away");

function ShotDetail({ G, s }: { G: Sheet; s: Shot }) {
  const reb = s.reb !== "NONE" ? ` · rebound off a ${({ SHOT: "save", MISS: "miss", BLOCK: "block" } as Record<string, string>)[s.reb] ?? "shot"}` : "";
  return (
    <div className="leading-relaxed">
      <div><b className="font-semibold">{pname(G, s.shooter)}</b> <span className={sideClass(G, s.team)}>{s.team}</span></div>
      <div>{EVN[s.ev]}, {shotNoun(s.type)}{s.ev === "SHOT" && s.goalie ? ` (${lastName(G, s.goalie)})` : ""}</div>
      <div>xG <b className="tabular font-semibold">{s.xg.toFixed(3)}</b>, {SIT[s.sit] ?? s.sit}</div>
      <div className="text-muted-foreground">{ORD(s.p)} {toi(s.t)}{reb}{s.rush ? " · rush" : ""}</div>
    </div>
  );
}

/** Rink with every shot, sized by xG. Away shoots left, home shoots right. */
export function ShotMap() {
  const { G, sel, pick, mapRef } = useShots();
  const [blocks, setBlocks] = React.useState(false);
  const [hover, setHover] = React.useState<{ s: Shot; x: number; y: number } | null>(null);
  const H = G.home.abbrev;
  const shots = G.shots.filter(s => blocks || s.ev !== "BLOCK");
  // Draw the selected shot last so it sits above its neighbours.
  const ordered = sel == null ? shots : [...shots.filter(s => s.i !== sel), ...shots.filter(s => s.i === sel)];
  const place = (s: Shot) => {
    const home = s.team === H;
    return { x: home ? s.x : -s.x, y: home ? -s.y : s.y, col: home ? "var(--home)" : "var(--away)", side: home ? "h" : "a" };
  };
  const selShot = sel != null ? G.shots[sel] : null;
  return (
    <Block title="Shot map" aside={
      <label className="flex cursor-pointer items-center gap-2 text-[13px] text-muted-foreground">
        <Switch checked={blocks} onCheckedChange={setBlocks} className="bg-muted [box-shadow:inset_0_0_0_1px_var(--border)] data-[state=checked]:bg-foreground data-[state=checked]:[box-shadow:none]" />Blocked shots
      </label>
    }>
        <svg ref={mapRef} viewBox="-102 -45 204 90" role="img" aria-label="Shot map" className="block h-auto w-full">
          <RinkMarks />
          {ordered.map(s => {
            const { x, y, col, side } = place(s);
            if (s.ev === "BLOCK") {
              return (
                <g key={s.i} stroke={col} strokeWidth={0.6} opacity={0.55}>
                  <line x1={x - 1.2} y1={y - 1.2} x2={x + 1.2} y2={y + 1.2} />
                  <line x1={x - 1.2} y1={y + 1.2} x2={x + 1.2} y2={y - 1.2} />
                </g>
              );
            }
            const goal = s.ev === "GOAL", on = sel === s.i;
            // Styling lives in globals.css (.shot): a hundred circles with
            // inline paint attributes were a big share of each game page.
            return (
              <circle key={s.i} cx={x.toFixed(1)} cy={y.toFixed(1)} r={shotRadius(s.xg).toFixed(2)}
                className={cn("shot", side, goal && "g", on && "on", sel != null && !on && "dim")}
                onMouseMove={e => setHover({ s, x: e.clientX, y: e.clientY })}
                onMouseLeave={() => setHover(null)}
                onClick={() => pick(s.i)} />
            );
          })}
          {selShot && selShot.ev !== "BLOCK" && (() => {
            const { x, y } = place(selShot);
            return <circle cx={x} cy={y} r={shotRadius(selShot.xg) + 2.6} fill="none" stroke="var(--brand)" strokeWidth={0.9}
              className="pointer-events-none animate-[ring_1.2s_ease-out_2]" />;
          })()}
        </svg>
        {/* Which end each side shoots at (their xG is in the strip above). */}
        <div className="mt-2 flex items-baseline justify-between gap-3 text-[13px]">
          <span className="font-semibold text-away">← {G.away.abbrev} shoots</span>
          <span className="text-xs text-muted-foreground max-sm:hidden">size = xG · ringed = goal</span>
          <span className="font-semibold text-home">{H} shoots →</span>
        </div>
        <div aria-live="polite">
          {selShot && (
            <div className="well relative mt-3 rounded-lg py-2.5 pl-3 pr-20 text-[13px]">
              <ShotDetail G={G} s={selShot} />
              <Button size="sm" variant="secondary" className="absolute right-2 top-2" onClick={() => pick(selShot.i)}>Clear</Button>
            </div>
          )}
        </div>
        {hover && (
          <div className="pointer-events-none fixed z-50 max-w-64 rounded-md border border-border bg-popover px-2.5 py-2 text-xs [box-shadow:var(--shadow-l)]"
            style={{ left: Math.min(hover.x + 14, innerWidth - 270), top: hover.y + 14 }}>
            <ShotDetail G={G} s={hover.s} />
          </div>
        )}
    </Block>
  );
}

/** Row props that pick a shot on click or Enter. */
function useShotRow() {
  const { sel, pick } = useShots();
  return (i: number) => ({
    tabIndex: 0,
    title: "Show on the rink",
    "data-state": sel === i ? "selected" : undefined,
    className: "cursor-pointer",
    onClick: () => pick(i, true),
    onKeyDown: (e: React.KeyboardEvent) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(i, true); } },
  });
}

const head = "h-9 px-2.5 text-xs font-medium normal-case tracking-normal";
const cell = "whitespace-nowrap px-2.5 py-2";

export function BestChances({ n = 5 }: { n?: number }) {
  const { G } = useShots();
  const row = useShotRow();
  return (
    <Table className="tabular text-[13px]">
      <TableHeader className="bg-transparent">
        <TableRow className="hover:bg-transparent">
          <TableHead className={head}>Shooter</TableHead><TableHead className={head}>When</TableHead>
          <TableHead className={cn(head, "text-right")}>xG</TableHead><TableHead className={head}>Result</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {bestChances(G, n).map(s => (
          <TableRow key={s.i} {...row(s.i)}>
            <TableCell className={cell}><span className={sideClass(G, s.team)}>{s.team}</span> {pname(G, s.shooter)}</TableCell>
            <TableCell className={cn(cell, "text-muted-foreground")}>{ORD(s.p)} {toi(s.t)}</TableCell>
            <TableCell className={cn(cell, "text-right font-semibold")}>{s.xg.toFixed(2)}</TableCell>
            <TableCell className={cell}>
              {s.ev === "GOAL" ? <b className="font-semibold text-brand">Goal</b> : s.ev === "SHOT" ? <>Saved <span className="text-muted-foreground">({lastName(G, s.goalie)})</span></> : "Missed"}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export function Scoring() {
  const { G } = useShots();
  const row = useShotRow();
  const goals = scoring(G);
  return (
    <Table className="tabular text-[13px]">
      <TableHeader className="bg-transparent">
        <TableRow className="hover:bg-transparent">
          <TableHead className={head}>Period</TableHead><TableHead className={head}>Goal</TableHead>
          <TableHead className={cn(head, "text-right")}>xG</TableHead><TableHead className={cn(head, "text-right")}>Score</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {goals.length === 0 && <TableRow><TableCell colSpan={4} className={cn(cell, "text-muted-foreground")}>No goals.</TableCell></TableRow>}
        {goals.map(({ s, score, assists }) => (
          <TableRow key={s.i} {...row(s.i)}>
            <TableCell className={cn(cell, "text-muted-foreground")}>{ORD(s.p)} {toi(s.t)}</TableCell>
            <TableCell className={cn(cell, "whitespace-normal")}>
              <span className={sideClass(G, s.team)}>{s.team}</span> <b className="font-semibold">{pname(G, s.shooter)}</b>
              <div className="text-xs text-muted-foreground">
                {assists.length ? assists.join(", ") : "Unassisted"}; {SIT[s.sit] ?? s.sit}{s.reb !== "NONE" ? ", rebound" : ""}, {shotNoun(s.type)}
              </div>
            </TableCell>
            <TableCell className={cn(cell, "text-right")}>{s.xg.toFixed(2)}</TableCell>
            <TableCell className={cn(cell, "text-right font-semibold")}>{score}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
