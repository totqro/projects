"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { seasonLabel } from "@/lib/format";

const SECTIONS = [
  { key: "games", label: "Games", match: (p: string) => p === "/" || p.startsWith("/game") },
  { key: "teams", label: "Teams", match: (p: string) => p.startsWith("/team") },
  { key: "players", label: "Players", match: (p: string) => p.startsWith("/player") },
  { key: "model", label: "Model", match: (p: string) => p.startsWith("/model") },
] as const;

/** The season in the current path, if the page has one. */
function pathSeason(path: string) {
  const m = path.match(/^\/(games|teams|players|team)\/(\d{4})/);
  if (m) return +m[2];
  const g = path.match(/^\/game\/(\d{4})/);
  return g ? +g[1] : null;
}

/** Primary navigation: a recessed track with the active section raised. */
export function SiteNav({ current }: { current: number }) {
  const path = usePathname() ?? "/";
  const season = pathSeason(path) ?? current;
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
  const path = usePathname() ?? "/";
  const router = useRouter();
  const season = pathSeason(path) ?? current;
  const go = (s: number) => {
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
