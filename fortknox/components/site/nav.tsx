"use client";

import Link from "next/link";
import { useEffect, useSyncExternalStore } from "react";
import { usePathname, useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { seasonLabel } from "@/lib/format";

const SECTIONS = [
  { key: "games", label: "Games", match: (p: string) => p === "/" || p.startsWith("/game") },
  { key: "teams", label: "Teams", match: (p: string) => p.startsWith("/team") },
  { key: "players", label: "Players", match: (p: string) => p.startsWith("/player") },
  { key: "model", label: "Model", match: (p: string) => p.startsWith("/model") },
] as const;

/** The season in the current path, if the page has one ("/" is the current
 *  season's games). */
function pathSeason(path: string, current: number) {
  if (path === "/") return current;
  const m = path.match(/^\/(games|teams|players|team)\/(\d{4})/);
  if (m) return +m[2];
  const g = path.match(/^\/game\/(\d{4})/);
  return g ? +g[1] : null;
}

// The last season the reader was in, for pages without one in the path
// (/model, /player/<id>), so moving to them doesn't reset the picker. Kept
// for the tab's session.
const KEY = "season";
const listeners = new Set<() => void>();
let picked: number | null = null;
function readPicked() {
  if (picked == null) try { picked = Number(sessionStorage.getItem(KEY)) || null; } catch {}
  return picked;
}
function setPicked(s: number) {
  if (s === readPicked()) return;
  picked = s;
  try { sessionStorage.setItem(KEY, String(s)); } catch {}
  listeners.forEach(f => f());
}
const subscribe = (f: () => void) => (listeners.add(f), () => { listeners.delete(f); });

/** The season last picked in the nav, for pages without one in the path (a
 *  player page shows that season). Null until something is picked. */
export const usePickedSeason = () => useSyncExternalStore(subscribe, readPicked, () => null);
export { setPicked as pickSeason };

/** The season the nav should show: the page's own, else the last one picked. */
function useSeason(current: number) {
  const path = usePathname() ?? "/";
  const own = pathSeason(path, current);
  const last = useSyncExternalStore(subscribe, readPicked, () => null);
  useEffect(() => { if (own != null) setPicked(own); }, [own]);
  return { path, season: own ?? last ?? current, own };
}

/** Primary navigation: a recessed track with the active section raised. */
export function SiteNav({ current }: { current: number }) {
  const { path, season } = useSeason(current);
  const href = (k: string) =>
    k === "games" ? (season === current ? "/" : `/games/${season}`) : k === "model" ? "/model" : `/${k}/${season}`;
  return (
    <nav aria-label="Sections" className="slot-nav inline-flex gap-0.5 rounded-[0.75rem] bg-card p-1 [box-shadow:var(--shadow-inset-deep)]">
      {SECTIONS.map(s => {
        const on = s.match(path);
        return (
          <Link key={s.key} href={href(s.key)} aria-current={on ? "page" : undefined}
            className={cn(
              "rounded-[0.5625rem] px-3.5 py-1.5 text-sm font-medium text-muted-foreground transition-[color,background,box-shadow]",
              "hover:text-foreground",
              on && "pill text-pressed text-foreground",
            )}>
            {s.label}
          </Link>
        );
      })}
    </nav>
  );
}

/** Season picker. Moves to the same section in the chosen season. */
export function SeasonSelect({ seasons, current }: { seasons: number[]; current: number }) {
  const router = useRouter();
  const { path, season, own } = useSeason(current);
  const go = (s: number) => {
    // Pages without a season stay put: a player page switches to the pick,
    // and it carries to the next section opened.
    if (own == null) return setPicked(s);
    if (path.startsWith("/teams")) return router.push(`/teams/${s}`);
    if (path.startsWith("/players")) return router.push(`/players/${s}`);
    if (path.startsWith("/team/")) return router.push(path.replace(/^\/team\/\d{4}/, `/team/${s}`));
    router.push(s === current ? "/" : `/games/${s}`);
  };
  return (
    <label className="flex items-center gap-2 text-sm text-muted-foreground">
      <span className="sr-only sm:not-sr-only">Season</span>
      <select value={season} onChange={e => go(+e.target.value)}
        className="h-9 rounded-lg bg-input px-2.5 text-sm text-foreground [box-shadow:var(--shadow-inset)] outline-none focus-visible:ring-2 focus-visible:ring-ring">
        {seasons.map(s => <option key={s} value={s}>{seasonLabel(s)}</option>)}
      </select>
    </label>
  );
}
