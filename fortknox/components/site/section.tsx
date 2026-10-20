import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/** A titled card: the page's standard panel. */
export function Panel({ title, aside, children, className, contentClassName, titleClassName }: {
  title: React.ReactNode;
  aside?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  contentClassName?: string;
  titleClassName?: string;
}) {
  return (
    <Card className={cn("min-w-0", className)}>
      <CardHeader className="flex-row items-center justify-between gap-3 pb-3">
        <CardTitle className={titleClassName}>{title}</CardTitle>
        {aside}
      </CardHeader>
      <CardContent className={contentClassName}>{children}</CardContent>
    </Card>
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
        <h2 className="text-base font-semibold tracking-[-0.015em]">{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

/** A recessed figure: label over a value. */
export function Tile({ label, children, className }: { label: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("well rounded-lg px-3 py-2.5", className)}>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="tabular mt-0.5 text-xl font-semibold tracking-[-0.02em]">{children}</div>
    </div>
  );
}

export function Note({ children, className }: { children: React.ReactNode; className?: string }) {
  return <p className={cn("text-[13px] leading-relaxed text-muted-foreground", className)}>{children}</p>;
}
