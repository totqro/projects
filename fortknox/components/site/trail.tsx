"use client";

import Link from "next/link";
import { useLayoutEffect, useState, useSyncExternalStore } from "react";

// This tab's path through the site, so a page can offer "back to where you
// came from" and know it matches what the browser's back would do. Every
// history entry is stamped with [session id, index in the trail]
// (history.state.hs); Next keeps custom history state on back/forward and
// reloads, and the patches below stamp each push and carry the stamp across
// every replace. The trail itself lives in sessionStorage, so it survives a
// reload and the full page loads that older games take. An entry stamped by
// another session (the tab left the site and came back by typing a URL, say)
// starts a fresh trail: what came before it is unknown, never guessed.

interface Stop { url: string; title: string }

const KEY = "trail";
let sid = "";
let trail: Stop[] = [];
let at = 0;
const listeners = new Set<() => void>();

const path = (url: string | URL) => { const u = new URL(url, location.href); return u.pathname + u.search; };
const here = () => path(location.href);
/** The page's title without the site name; the home page has only that. */
const siteTitle = () => (location.pathname === "/" ? "home" : document.title.replace(/ · High Slot$/, ""));
type Stamp = [string, number];
const stampOf = (state: unknown): Stamp | null => {
  const hs = (state as { hs?: unknown } | null)?.hs;
  return Array.isArray(hs) && typeof hs[0] === "string" && typeof hs[1] === "number" ? (hs as Stamp) : null;
};

function changed() {
  try { sessionStorage.setItem(KEY, JSON.stringify({ sid, trail, at })); } catch {}
  // Pushes arrive from Next's insertion effect, where React allows no updates.
  queueMicrotask(() => listeners.forEach(f => f()));
}

function fresh() {
  sid = Math.random().toString(36).slice(2, 10);
  trail = [];
  at = 0;
}

function init() {
  let saved: { sid?: unknown; trail?: unknown; at?: unknown } = {};
  try { saved = JSON.parse(sessionStorage.getItem(KEY) ?? "{}"); } catch {}
  const ok = typeof saved.sid === "string" && Array.isArray(saved.trail) && typeof saved.at === "number";
  const stamp = stampOf(history.state);
  if (ok) { sid = saved.sid as string; trail = saved.trail as Stop[]; at = saved.at as number; }
  if (ok && stamp && stamp[0] === sid) {
    // A reload, or back/forward onto a page loaded in full.
    at = stamp[1];
  } else if (ok && !stamp && history.length > 1 && document.referrer && new URL(document.referrer).origin === location.origin) {
    // A full page load from the trail's current page (an older game).
    at += 1;
    trail.length = at;
  } else {
    fresh();
  }
  history.replaceState({ ...history.state, hs: [sid, at] }, "");
  trail[at] = { url: here(), title: siteTitle() };
  changed();

  const push = history.pushState.bind(history);
  const replace = history.replaceState.bind(history);
  history.pushState = (data, unused, url) => {
    at += 1;
    trail.length = at;
    trail[at] = { url: url ? path(url) : here(), title: siteTitle() };
    changed();
    return push({ ...data, hs: [sid, at] }, unused, url);
  };
  history.replaceState = (data, unused, url) => {
    const r = replace({ ...data, hs: [sid, at] }, unused, url);
    if (url) { trail[at] = { ...trail[at], url: here() }; changed(); }
    return r;
  };
  addEventListener("popstate", e => {
    const s = stampOf(e.state);
    if (s && s[0] === sid) at = s[1];
    else {
      // Unstamped: a plain #anchor link just made this entry. Stamped by
      // another session: what came before it is unknown.
      if (s) fresh(); else { at += 1; trail.length = at; }
      replace({ ...history.state, hs: [sid, at] }, "");
    }
    trail[at] = { url: here(), title: trail[at]?.title ?? siteTitle() };
    changed();
  });
  // Titles settle after the URL does (metadata, and older games set theirs
  // once their sheet loads), so keep the current stop's title current.
  new MutationObserver(() => {
    if (trail[at] && trail[at].url === here() && trail[at].title !== siteTitle()) {
      trail[at] = { ...trail[at], title: siteTitle() };
      changed();
    }
  }).observe(document.head, { subtree: true, childList: true, characterData: true });
}

// Before Next's router mounts, so its history patches wrap these.
if (typeof window !== "undefined" && !(window as { __trail?: boolean }).__trail) {
  (window as { __trail?: boolean }).__trail = true;
  init();
}

const subscribe = (f: () => void) => { listeners.add(f); return () => { listeners.delete(f); }; };

/** The page the browser's back button returns to, as "url\ntitle", or "" when
 *  that isn't a page of this site seen in this tab. */
function previous() {
  const p = at > 0 ? trail[at - 1] : undefined;
  return p ? `${p.url}\n${p.title}` : "";
}

/** Rendered once in the root layout so every page joins the trail. */
export function Trail() { return null; }

/** "← Back to <the page you came from>" when that was a page of this site, as
 *  the browser's back would take you; otherwise a plain link to `href`. Key it
 *  by page so it remounts with each one. */
export function BackLink({ href, label, className }: { href: string; label: string; className?: string }) {
  const prev = useSyncExternalStore(subscribe, previous, () => "");
  // A page renders before Next pushes its history entry, so the trail only
  // speaks for this page from the commit on; layout effects run after it,
  // before paint.
  const [ready, setReady] = useState(false);
  useLayoutEffect(() => setReady(true), []);
  if (!ready || !prev) return <Link href={href} className={className}>&larr; {label}</Link>;
  const [url, title] = prev.split("\n");
  return (
    <Link href={url} className={className} title={title}
      onClick={e => {
        // A modified click opens the page anew; a plain one is the browser's back.
        if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        e.preventDefault();
        history.back();
      }}>
      &larr; Back to {title || "previous page"}
    </Link>
  );
}
