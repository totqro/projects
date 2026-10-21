"use client";

import * as React from "react";
import Link from "next/link";
import { X } from "lucide-react";

// Closed for the rest of this visit, so it doesn't come back on every return
// to the games feed; a reload brings it back.
let closed = false;

/** Shown above the games feed on every visit until the reader closes it. */
export function Intro() {
  const [hidden, setHidden] = React.useState(closed);
  if (hidden) return null;
  const close = () => { closed = true; setHidden(true); };
  return (
    <aside className="well relative mb-6 rounded-xl py-3.5 pl-4 pr-12 text-[14px] leading-relaxed text-secondary-foreground">
      <b className="font-semibold text-foreground">Every NHL game, scored shot by shot.</b>{" "}
      Each shot gets an expected-goals (xG) value: the chance an average shooter scores from there. Add them up and you see who earned the result.
      A <span className="whitespace-nowrap font-medium text-foreground">−xG win</span> is a win by the team with fewer chances.{" "}
      <Link href="/about#glossary" className="text-foreground underline underline-offset-4">Glossary</Link>{" · "}
      <Link href="/model" className="text-foreground underline underline-offset-4">How the model works</Link>
      <button type="button" onClick={close} aria-label="Hide this introduction"
        className="absolute right-2 top-2 grid size-8 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground">
        <X className="size-4" />
      </button>
    </aside>
  );
}

