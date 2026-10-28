/** A page's title and its one supporting line, with any action (`children`)
 *  in the top right corner, level with the title. */
export function PageHead({ title, sub, children }: { title: React.ReactNode; sub?: React.ReactNode; children?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0">
        <h1 className="slot-headline font-[family-name:var(--font-display)] text-[clamp(26px,3.6vw,36px)] font-bold leading-tight tracking-[-0.03em]">{title}</h1>
        {sub && <p className="mt-1.5 text-[15px] text-muted-foreground">{sub}</p>}
      </div>
      {children}
    </div>
  );
}
