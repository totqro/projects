import { cn } from "@/lib/utils";

/** Section headings site-wide: Big Shoulders capitals. */
export const HEADING = "font-[family-name:var(--font-display)] text-[22px] font-extrabold uppercase leading-none tracking-[0.02em]";

/** A titled panel. No box: the title in the display face over its content,
 *  set apart by space (the cards it once drew made every page a dashboard). */
export function Panel({ title, aside, children, className, contentClassName, titleClassName }: {
  title: React.ReactNode;
  aside?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  contentClassName?: string;
  titleClassName?: string;
}) {
  return (
    <section className={cn("min-w-0", className)}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h2 className={cn(HEADING, titleClassName)}>{title}</h2>
        {aside}
      </div>
      <div className={contentClassName}>{children}</div>
    </section>
  );
}

/** A heading over a self-contained surface such as a table. */
export function Section({ title, aside, children, className, id }: {
  title: React.ReactNode;
  aside?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <section id={id} className={cn("min-w-0", className)}>
      <div className="mb-2.5 flex flex-wrap items-end justify-between gap-3">
        <h2 className={HEADING}>{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

/** A section with no box around it: its heading over the content, set apart
 *  by space. The game page's frame. */
export function Block({ title, aside, children, className }: {
  title: React.ReactNode;
  aside?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("min-w-0", className)}>
      <div className="mb-3 flex min-h-7 items-center justify-between gap-3">
        <h2 className={HEADING}>{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

/** A figure: a small label over the number, under a rule (the stat strip's look). */
export function Tile({ label, children, className }: { label: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-col border-t border-foreground/70 pb-1 pr-3 pt-2", className)}>
      <div className="text-xs font-semibold uppercase tracking-[0.06em] text-muted-foreground">{label}</div>
      <div className="tabular mt-auto pt-1 font-[family-name:var(--font-display)] text-[26px] font-extrabold leading-none">{children}</div>
    </div>
  );
}

export function Note({ children, className }: { children: React.ReactNode; className?: string }) {
  return <p className={cn("text-[13px] leading-relaxed text-muted-foreground", className)}>{children}</p>;
}

/** A row of labelled figures between rules, like the game page's stat strip. */
export function StatStrip({ items, className }: { items: [label: string, value: React.ReactNode][]; className?: string }) {
  return (
    <dl className={cn("grid grid-cols-2 border-y border-foreground/80 sm:grid-flow-col sm:auto-cols-fr sm:grid-cols-none", className)}>
      {items.map(([k, v], i) => (
        <div key={k} className={cn("px-4 py-2.5 first:pl-0 max-sm:odd:pl-0", i > 0 && "sm:border-l sm:border-border", i % 2 === 1 && "max-sm:border-l max-sm:border-border", i >= 2 && "max-sm:border-t max-sm:border-border")}>
          <dt className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">{k}</dt>
          <dd className="tabular mt-1 font-[family-name:var(--font-display)] text-[26px] font-extrabold leading-none">{v}</dd>
        </div>
      ))}
    </dl>
  );
}
