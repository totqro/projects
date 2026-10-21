"use client";

import { useId } from "react";
import { cn } from "@/lib/utils";
import { teamName } from "@/lib/teams";
import { teamColor } from "@/lib/team-colors";
import { Dropdown, type DropdownOption } from "@/components/site/dropdown";

/** A labelled dropdown, the filter bars' building block. `teams` marks the
 *  values as team abbreviations: each option gets its colour and full name. */
export function SelectField({ label, value, onChange, options, teams, className }: {
  label: string;
  value: string | number;
  onChange: (v: string) => void;
  options: (string | number | [value: string | number, label: string])[];
  teams?: boolean;
  className?: string;
}) {
  const labelId = useId();
  const opts: DropdownOption[] = options.map(o => {
    const [v, l] = Array.isArray(o) ? o : [o, String(o)];
    const ab = String(v);
    return teams && ab && teamColor(ab)
      ? { value: ab, label: teamName(ab), tag: ab, swatch: teamColor(ab) }
      : { value: String(v), label: l };
  });
  return (
    <div className={cn("flex flex-col gap-1 text-xs text-muted-foreground", className)}>
      <span id={labelId}>{label}</span>
      <Dropdown labelId={labelId} value={String(value)} onChange={onChange} options={opts} />
    </div>
  );
}
