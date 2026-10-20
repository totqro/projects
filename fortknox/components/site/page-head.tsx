/** A page's title and its one supporting line. */
export function PageHead({ title, sub, children }: { title: React.ReactNode; sub?: React.ReactNode; children?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="vault-headline font-[family-name:var(--font-display)] text-[clamp(26px,3.6vw,36px)] font-bold leading-tight tracking-[-0.03em]">{title}</h1>
        {sub && <p className="mt-1.5 text-[15px] text-muted-foreground">{sub}</p>}
      </div>
      {children}
    </div>
  );
}
