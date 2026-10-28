"use client";

import { useSyncExternalStore } from "react";

/** Set on <html> before first paint by THEME_SCRIPT: the reader's pick from
 *  localStorage, else the system setting. */
export const THEME_KEY = "theme";
/** "cvd" when the reader turned on colour-blind-safe colours (html.cvd). */
export const PALETTE_KEY = "palette";
export const THEME_SCRIPT = `(function(){try{var t=localStorage.getItem("${THEME_KEY}");if(t!=="light"&&t!=="dark")t=matchMedia("(prefers-color-scheme: light)").matches?"light":"dark";var c=document.documentElement.classList;c.remove("dark","light");c.add(t);c.toggle("cvd",localStorage.getItem("${PALETTE_KEY}")==="cvd")}catch(e){}})()`;

const listeners = new Set<() => void>();
const read = () => (document.documentElement.classList.contains("light") ? "light" : "dark");
const subscribe = (f: () => void) => (listeners.add(f), () => { listeners.delete(f); });

function setTheme(t: "light" | "dark") {
  const c = document.documentElement.classList;
  c.remove("dark", "light");
  c.add(t);
  try { localStorage.setItem(THEME_KEY, t); } catch {}
  listeners.forEach(f => f());
}

/** Light/dark switch for the masthead. */
export function ThemeToggle() {
  const theme = useSyncExternalStore(subscribe, read, () => "dark");
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button type="button" onClick={() => setTheme(next)} aria-label={`Switch to ${next} mode`} title={`Switch to ${next} mode`}
      className="grid size-9 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-[color-mix(in_oklch,var(--foreground)_7%,transparent)] hover:text-foreground">
      {theme === "dark" ? (
        <svg viewBox="0 0 20 20" className="size-[18px]" aria-hidden="true">
          <circle cx="10" cy="10" r="3.6" fill="none" stroke="currentColor" strokeWidth="1.6" />
          <path d="M10 2v2M10 16v2M2 10h2M16 10h2M4.3 4.3l1.4 1.4M14.3 14.3l1.4 1.4M4.3 15.7l1.4-1.4M14.3 5.7l1.4-1.4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      ) : (
        <svg viewBox="0 0 20 20" className="size-[18px]" aria-hidden="true">
          <path d="M16.5 12.2A6.8 6.8 0 0 1 7.8 3.5a6.8 6.8 0 1 0 8.7 8.7Z" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
        </svg>
      )}
    </button>
  );
}

const readCvd = () => document.documentElement.classList.contains("cvd");

function setCvd(on: boolean) {
  document.documentElement.classList.toggle("cvd", on);
  try { if (on) localStorage.setItem(PALETTE_KEY, "cvd"); else localStorage.removeItem(PALETTE_KEY); } catch {}
  listeners.forEach(f => f());
}

/** Colour-blind-safe colours on/off, for the masthead. */
export function PaletteToggle() {
  const on = useSyncExternalStore(subscribe, readCvd, () => false);
  const label = on ? "Use standard colours" : "Use colour-blind-safe colours";
  return (
    <button type="button" onClick={() => setCvd(!on)} aria-pressed={on} aria-label="Colour-blind-safe colours" title={label}
      className={"grid size-9 place-items-center rounded-lg transition-colors hover:bg-[color-mix(in_oklch,var(--foreground)_7%,transparent)] hover:text-foreground " + (on ? "text-foreground" : "text-muted-foreground")}>
      <svg viewBox="0 0 20 20" className="size-[18px]" aria-hidden="true">
        <path d="M1.8 10S4.8 4.6 10 4.6 18.2 10 18.2 10 15.2 15.4 10 15.4 1.8 10 1.8 10Z" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
        <circle cx="10" cy="10" r="2.6" fill={on ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.6" />
      </svg>
    </button>
  );
}
