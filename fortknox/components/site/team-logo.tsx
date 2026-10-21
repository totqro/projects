import Image from "next/image";
import { cn } from "@/lib/utils";

/** A team's logo in the NHL's own two versions, served from public/logos/
 *  so a change on the NHL's side can't blank every logo here: the
 *  dark-background one in dark mode, the light-background one (logos/light/)
 *  in light mode. CSS (.logo-dark/.logo-light) shows the one that fits. */
export function TeamLogo({ team, size = 20, className }: { team: string; size?: number; className?: string }) {
  const img = (src: string, which: string) => (
    <Image src={src} alt="" width={size} height={size}
      className={cn("inline-block shrink-0 object-contain", which, className)} style={{ width: size, height: size }} />
  );
  return (
    <>
      {img(`/logos/${team}.svg`, "logo-dark")}
      {img(`/logos/light/${team}.svg`, "logo-light")}
    </>
  );
}
