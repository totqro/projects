"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { BRANDS, type BrandKey } from "./brands";

const KEY = "rebrand-theme";

/** Floating picker for the rebrand samples. Remembers the pick per browser
 *  and accepts ?theme=<key> so a link opens straight into one. */
export function ThemeSwitcher() {
  const [on, setOn] = useState<BrandKey>("fortknox");
  const [open, setOpen] = useState(true);

  useEffect(() => {
    let t: string | null = new URLSearchParams(location.search).get("theme");
    try { t ??= localStorage.getItem(KEY); } catch {}
    if (t && BRANDS.some(b => b.key === t)) apply(t as BrandKey);
  }, []);

  function apply(k: BrandKey) {
    setOn(k);
    document.documentElement.dataset.theme = k;
    try { localStorage.setItem(KEY, k); } catch {}
  }

  return (
    <div className="fixed bottom-4 right-4 z-50 w-60 rounded-xl border bg-popover p-2 text-sm [box-shadow:var(--shadow-xl)]">
      <button onClick={() => setOpen(o => !o)} className="flex w-full items-center justify-between px-2 py-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">
        Rebrand samples <span>{open ? "–" : "+"}</span>
      </button>
      {open && (
        <ul className="mt-1 space-y-0.5">
          {BRANDS.map((b, i) => (
            <li key={b.key}>
              <button onClick={() => apply(b.key)}
                className={cn("w-full rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-accent", on === b.key && "pill")}>
                <span className="font-medium">{i ? `${i}. ` : ""}{b.name}</span>
                <span className="block text-xs text-muted-foreground">{b.note}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
