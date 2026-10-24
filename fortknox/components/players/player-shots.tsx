"use client";

import * as React from "react";
import { f1, ORD, toi } from "@/lib/format";
import { shotNoun } from "@/lib/teams";
import { RinkMarks, shotRadius } from "@/components/charts/rink";
import { Note } from "@/components/site/section";
import { Segmented } from "@/components/teams/teams-view";

/** One unblocked shot, compact for the page payload:
 *  [x, y, xg, event (G goal, S saved, M missed), type, period, time, game index]. */
export type PlayerShot = [x: number, y: number, xg: number, ev: "G" | "S" | "M", type: string, p: number, t: number, game: number];

const EV = { G: "goal", S: "saved", M: "missed" } as const;

const WINDOWS: [string, string, number][] = [["season", "Season", Infinity], ["20", "Last 20", 20], ["10", "Last 10", 10], ["5", "Last 5", 5]];

/** A player's unblocked shots on the attacking half, sized by xG; goals are
 *  filled. Blocks are left out: their spot is where the block happened.
 *  Drawn in the browser: as server markup, the dots and their labels were
 *  the biggest part of a player page. `games` is every game he played that
 *  season, oldest first, so a window keeps the shots of his last N games. */
export function PlayerShotMap({ shots, games }: { shots: PlayerShot[]; games: string[] }) {
  const [ready, setReady] = React.useState(false);
  const [hover, setHover] = React.useState<{ s: PlayerShot; x: number; y: number } | null>(null);
  const [win, setWin] = React.useState("season");
  React.useEffect(() => setReady(true), []);
  const n = Math.min(WINDOWS.find(w => w[0] === win)![2], games.length);
  const shown = React.useMemo(() => shots.filter(s => s[7] >= games.length - n), [shots, games.length, n]);
  // Goals last so they sit on top of the misses around them.
  const ordered = React.useMemo(() => [...shown.filter(s => s[3] !== "G"), ...shown.filter(s => s[3] === "G")], [shown]);
  const windows = WINDOWS.filter(([, , w]) => w === Infinity || w < games.length);
  return (
    <div>
      {windows.length > 1 && (
        <div className="mb-3">
          <Segmented label="Games shown" value={win} onChange={setWin} options={windows.map(([k, l]) => [k, l] as [string, string])} />
        </div>
      )}
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
      <Note className="mt-2 text-xs">
        {win === "season" ? "" : `Last ${n} games: `}{shown.length} unblocked shots, {f1(shown.reduce((a, s) => a + s[2], 0))} xG, {shown.filter(s => s[3] === "G").length} goals. Attacking to the right; hover a dot for the shot.
      </Note>
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
