"use client";

import * as React from "react";
import { ORD, toi } from "@/lib/format";
import { shotNoun } from "@/lib/teams";
import { RinkMarks, shotRadius } from "@/components/charts/rink";

/** One unblocked shot, compact for the page payload:
 *  [x, y, xg, event (G goal, S saved, M missed), type, period, time, game index]. */
export type PlayerShot = [x: number, y: number, xg: number, ev: "G" | "S" | "M", type: string, p: number, t: number, game: number];

const EV = { G: "goal", S: "saved", M: "missed" } as const;

/** A player's unblocked shots on the attacking half, sized by xG; goals are
 *  filled. Blocks are left out: their spot is where the block happened.
 *  Drawn in the browser: as server markup, the dots and their labels were
 *  the biggest part of a player page. */
export function PlayerShotMap({ shots, games }: { shots: PlayerShot[]; games: string[] }) {
  const [ready, setReady] = React.useState(false);
  const [hover, setHover] = React.useState<{ s: PlayerShot; x: number; y: number } | null>(null);
  React.useEffect(() => setReady(true), []);
  // Goals last so they sit on top of the misses around them.
  const ordered = React.useMemo(() => [...shots.filter(s => s[3] !== "G"), ...shots.filter(s => s[3] === "G")], [shots]);
  return (
    <div>
      <svg viewBox="-1 -44 102 88" role="img" aria-label="Shot map, attacking to the right" className="block h-auto w-full max-w-xl">
        <RinkMarks id="pice" />
        {ready && ordered.map((s, i) => (
          <circle key={i} cx={s[0]} cy={-s[1]} r={shotRadius(s[2]).toFixed(2)} className={s[3] === "G" ? "pshot g" : "pshot"}
            onMouseMove={e => setHover({ s, x: e.clientX, y: e.clientY })} onMouseLeave={() => setHover(null)} />
        ))}
      </svg>
      <div className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span><i className="mr-1.5 inline-block size-2.5 rounded-full bg-brand align-[-1px]" />goal</span>
        <span><i className="mr-1.5 inline-block size-2.5 rounded-full border border-brand-dim align-[-1px]" />saved or missed</span>
        <span>size = xG</span>
      </div>
      {hover && (
        <div className="pointer-events-none fixed z-50 max-w-64 rounded-md border border-border bg-popover px-2.5 py-2 text-xs leading-relaxed [box-shadow:var(--shadow-l)]"
          style={{ left: Math.min(hover.x + 14, innerWidth - 270), top: hover.y + 14 }}>
          <div className="font-semibold">{games[hover.s[7]]}</div>
          <div>{shotNoun(hover.s[4])}, {EV[hover.s[3]]}</div>
          <div>xG <b className="tabular font-semibold">{hover.s[2].toFixed(3)}</b></div>
          <div className="text-muted-foreground">{ORD(hover.s[5])} {toi(hover.s[6])}</div>
        </div>
      )}
    </div>
  );
}
