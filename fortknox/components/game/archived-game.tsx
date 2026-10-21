"use client";

import * as React from "react";
import { usePathname } from "next/navigation";
import NotFound from "@/app/not-found";
import { fmtDate } from "@/lib/format";
import type { RawSheet } from "@/lib/types";
import { GameView } from "@/components/game/game-view";

/** An older season's game page: reads the id from the URL (/game/<id>, by way
 *  of the firebase.json rewrite), fetches that game's sheet and draws it. */
export function ArchivedGame() {
  const pathname = usePathname();
  const [state, setState] = React.useState<RawSheet | "loading" | "missing">("loading");
  React.useEffect(() => {
    const id = window.location.pathname.match(/^\/game\/(\d{10})\/?$/)?.[1];
    if (!id) return setState("missing");
    let live = true;
    setState("loading");
    fetch(`/data/${id.slice(0, 4)}/game/${id}.json`)
      .then(r => (r.ok ? (r.json() as Promise<RawSheet>) : null))
      .catch(() => null)
      .then(raw => {
        if (!live) return;
        setState(raw ?? "missing");
        if (raw) document.title = `${raw.away.abbrev} ${raw.away.score}, ${raw.home.abbrev} ${raw.home.score} (${fmtDate(raw.date)}) · High Slot`;
      });
    return () => { live = false; };
  }, [pathname]);
  if (state === "missing") return <NotFound />;
  if (state === "loading") return <p className="py-24 text-center text-sm text-muted-foreground">Loading game&hellip;</p>;
  return <GameView raw={state} />;
}
