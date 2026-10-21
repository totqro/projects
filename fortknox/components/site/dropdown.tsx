"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export type DropdownOption = {
  value: string;
  label: string;
  /** A colour bar beside the option, and a dot in the button: team pickers. */
  swatch?: string;
  /** A short tag before the label, such as the team's abbreviation. */
  tag?: string;
};

/** The site's own select: text and a chevron at rest, a list with check
 *  marks when open. A listbox with arrow keys, Home/End, type-to-jump,
 *  Enter to pick and Escape to close. Styled by .hs-dd in globals.css. */
export function Dropdown({ value, onChange, options, labelId, align = "start", className }: {
  value: string;
  onChange: (v: string) => void;
  options: DropdownOption[];
  /** The id of the visible label, read out with the current value. */
  labelId: string;
  align?: "start" | "end";
  className?: string;
}) {
  const id = React.useId();
  const [open, setOpen] = React.useState(false);
  const [active, setActive] = React.useState(0);
  const root = React.useRef<HTMLDivElement>(null);
  const btn = React.useRef<HTMLButtonElement>(null);
  const list = React.useRef<HTMLUListElement>(null);
  const cur = options.find(o => o.value === value) ?? options[0];
  const swatches = options.some(o => o.swatch);

  const show = () => {
    setActive(Math.max(0, options.findIndex(o => o.value === value)));
    setOpen(true);
  };
  const close = (refocus: boolean) => {
    setOpen(false);
    if (refocus) btn.current?.focus();
  };
  const choose = (i: number) => {
    close(true);
    if (options[i].value !== value) onChange(options[i].value);
  };

  React.useEffect(() => {
    if (!open) return;
    list.current?.focus({ preventScroll: true });
    const away = (e: PointerEvent) => { if (!root.current?.contains(e.target as Node)) close(false); };
    document.addEventListener("pointerdown", away);
    return () => document.removeEventListener("pointerdown", away);
  }, [open]);
  React.useEffect(() => {
    if (open) list.current?.querySelector(`[data-i="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [open, active]);

  const onKey = (e: React.KeyboardEvent) => {
    const last = options.length - 1;
    const move: Record<string, number> = { ArrowDown: active + 1, ArrowUp: active - 1, Home: 0, End: last };
    if (e.key in move) { e.preventDefault(); setActive(Math.min(last, Math.max(0, move[e.key]))); }
    else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); choose(active); }
    else if (e.key === "Escape") { e.preventDefault(); close(true); }
    else if (e.key === "Tab") close(false);
    else if (e.key.length === 1 && /\S/.test(e.key)) {
      // Jump to the next option starting with the key, by label or tag.
      const k = e.key.toLowerCase();
      const hit = (o: DropdownOption) => o.label.toLowerCase().startsWith(k) || !!o.tag?.toLowerCase().startsWith(k);
      for (let n = 1; n <= options.length; n++) {
        const i = (active + n) % options.length;
        if (hit(options[i])) { setActive(i); break; }
      }
    }
  };

  return (
    <div ref={root} className={cn("hs-dd", className)} data-open={open || undefined}>
      <button ref={btn} type="button" className="hs-dd-btn" aria-haspopup="listbox" aria-expanded={open}
        aria-controls={open ? `${id}-list` : undefined} aria-labelledby={`${labelId} ${id}-value`}
        onClick={() => (open ? close(true) : show())}
        onKeyDown={e => { if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); show(); } }}>
        {swatches && <span className="hs-dd-dot" style={{ "--sw": cur.swatch } as React.CSSProperties} data-none={!cur.swatch || undefined} />}
        <span id={`${id}-value`}>{cur.label}</span>
        <svg viewBox="0 0 16 16" className="hs-dd-chev" aria-hidden="true">
          <path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {open && (
        <ul ref={list} id={`${id}-list`} role="listbox" tabIndex={-1} aria-labelledby={labelId}
          aria-activedescendant={`${id}-o${active}`} className="hs-dd-list" data-align={align} onKeyDown={onKey}>
          {options.map((o, i) => (
            <li key={o.value} id={`${id}-o${i}`} data-i={i} role="option" aria-selected={o.value === value}
              data-active={i === active || undefined}
              onPointerDown={e => e.preventDefault()} onPointerMove={() => setActive(i)} onClick={() => choose(i)}>
              {swatches && <span className="hs-dd-bar" style={{ "--sw": o.swatch } as React.CSSProperties} />}
              {o.tag && <span className="hs-dd-tag">{o.tag}</span>}
              <span className="truncate">{o.label}</span>
              <svg viewBox="0 0 16 16" className="hs-dd-check" aria-hidden="true">
                <path d="M3.5 8.5l3 3 6-7" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
