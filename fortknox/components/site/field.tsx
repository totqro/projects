import { cn } from "@/lib/utils";
import { NativeSelect } from "@/components/ui/native-select";

/** A labelled native select, the filter bars' building block. */
export function SelectField({ label, value, onChange, options, className }: {
  label: string;
  value: string | number;
  onChange: (v: string) => void;
  options: (string | number | [value: string | number, label: string])[];
  className?: string;
}) {
  return (
    <label className={cn("flex flex-col gap-1 text-xs text-muted-foreground", className)}>
      {label}
      <NativeSelect value={value} onChange={e => onChange(e.target.value)} className="h-9 min-w-28 text-sm">
        {options.map(o => {
          const [v, l] = Array.isArray(o) ? o : [o, String(o)];
          return <option key={v} value={v}>{l}</option>;
        })}
      </NativeSelect>
    </label>
  );
}
