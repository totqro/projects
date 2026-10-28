"use client";

import { useSyncExternalStore } from "react";

/** Set on <html> before first paint by THEME_SCRIPT: the reader's pick from
 *  localStorage, else the system setting. */
export const THEME_KEY = "theme";
/** "cvd" when the reader turned on colour-blind-safe colours (html.cvd). */
export const PALETTE_KEY = "palette";
export const THEME_SCRIPT = `(function(){try{var t=localStorage.getItem("${THEME_KEY}");if(t!=="light"&&t!=="dark")t="light";var c=document.documentElement.classList;c.remove("dark","light");c.add(t);c.toggle("cvd",localStorage.getItem("${PALETTE_KEY}")==="cvd")}catch(e){}})()`;

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

const textButton = "whitespace-nowrap rounded px-2 py-1.5 text-[13px] font-medium transition-colors hover:text-foreground";

/** Light/dark switch for the masthead, as a word: the theme it switches to. */
export function ThemeToggle() {
  const theme = useSyncExternalStore(subscribe, read, () => "light");
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button type="button" onClick={() => setTheme(next)} title={`Switch to ${next} mode`} className={textButton + " text-muted-foreground"}>
      {next === "dark" ? "Dark" : "Light"}
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
  return (
    <button type="button" onClick={() => setCvd(!on)} aria-pressed={on} title={on ? "Use standard colours" : "Use colour-blind-safe colours"}
      className={textButton + (on ? " text-foreground underline decoration-[var(--brand)] decoration-2 underline-offset-4" : " text-muted-foreground")}>
      Colour-blind
    </button>
  );
}
