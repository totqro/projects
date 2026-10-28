"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { posLabel, TEAMS } from "@/lib/teams";

// The masthead's search: teams and this season's players, by name. The
// player list (app/data/[season]/search.json) loads the first time the box
// is used, so pages don't carry it.

type Player = [id: number, name: string, team: string, pos: string];
interface Hit { href: string; label: string; meta: string }

/** Lower case with accents dropped, so "stutzle" finds Stützle. */
const fold = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

export function SiteSearch({ season, wide }: { season: number; wide?: boolean }) {
  const router = useRouter();
  const [q, setQ] = React.useState("");
  const [players, setPlayers] = React.useState<Player[] | null>(null);
  const [open, setOpen] = React.useState(false);
  const [active, setActive] = React.useState(0);
  const listId = React.useId();

  const load = () => {
    if (players) return;
    setPlayers([]);
    fetch(`/data/${season}/search.json`).then(r => (r.ok ? r.json() : [])).then(setPlayers).catch(() => setPlayers([]));
  };

  const hits = React.useMemo<Hit[]>(() => {
    const t = fold(q.trim());
    if (t.length < 2) return [];
    const teams = Object.entries(TEAMS)
      .filter(([ab, [name]]) => fold(ab) === t || fold(name).includes(t))
      .map(([ab, [name]]) => ({ href: `/team/${season}/${ab}`, label: name, meta: "Team" }));
    const ps = (players ?? [])
      .filter(([, name]) => fold(name).split(" ").some(w => w.startsWith(t)) || fold(name).startsWith(t))
      .slice(0, 8)
      .map(([id, name, team, pos]) => ({ href: `/player/${id}`, label: name, meta: `${team} · ${posLabel(pos)}` }));
    return [...teams, ...ps].slice(0, 8);
  }, [q, players, season]);

  const go = (h: Hit) => { setOpen(false); setQ(""); router.push(h.href); };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setActive(a => Math.min(a + 1, hits.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive(a => Math.max(a - 1, 0)); }
    else if (e.key === "Enter" && hits[active]) { e.preventDefault(); go(hits[active]); }
    else if (e.key === "Escape") setOpen(false);
  };

  return (
    <div className={wide ? "relative w-full" : "relative"}>
      <label className="flex items-center gap-2.5 text-[13px] text-muted-foreground">
        <span className="sr-only sm:not-sr-only">Search</span>
        <input type="search" value={q} placeholder="Team or player" role="combobox" aria-expanded={open && hits.length > 0}
          aria-controls={listId} aria-autocomplete="list" autoComplete="off"
          onFocus={() => { load(); setOpen(true); }} onBlur={() => setTimeout(() => setOpen(false), 120)}
          onChange={e => { setQ(e.target.value); setActive(0); setOpen(true); }} onKeyDown={onKey}
          className={(wide ? "w-full " : "w-48 ") + "h-8 rounded-[3px] border border-border bg-card px-2.5 text-[13px] text-foreground placeholder:text-muted-foreground focus:outline-none focus-visible:ring-1 focus-visible:ring-[var(--brand)]"} />
      </label>
      {open && hits.length > 0 && (
        <ul id={listId} role="listbox" className="absolute right-0 top-[calc(100%+6px)] z-50 w-64 max-w-[calc(100vw-2rem)] overflow-hidden rounded-[3px] border border-border bg-popover py-1 text-[13.5px] shadow-lg">
          {hits.map((h, i) => (
            <li key={h.href} role="option" aria-selected={i === active}>
              <a href={h.href} onMouseDown={e => { e.preventDefault(); go(h); }} onMouseEnter={() => setActive(i)}
                className={"flex items-baseline justify-between gap-3 px-3 py-1.5 text-foreground " + (i === active ? "bg-accent" : "")}>
                <span className="truncate">{h.label}</span><span className="shrink-0 text-xs text-muted-foreground">{h.meta}</span>
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
