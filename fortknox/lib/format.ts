// Number and date formatting, shared by every page. Missing values print as
// an en dash.

const DASH = "–";
type N = number | null | undefined;

export const f1 = (v: N) => (v == null ? DASH : (+v).toFixed(1));
export const f2 = (v: N) => (v == null ? DASH : (+v).toFixed(2));
export const pct = (v: N, d = 1) => (v == null ? DASH : (v * 100).toFixed(d) + "%");
/** Save-percentage style: .912 */
export const sv = (v: N) => (v == null ? DASH : v.toFixed(3).replace(/^0/, ""));
/** +1.2 / -0.4, for differentials. Pair with tone() for the colour. */
export const signed = (v: N, d = 1) => (v == null ? DASH : (v > 0 ? "+" : "") + (+v).toFixed(d));
export const tone = (v: N): "pos" | "neg" | undefined => (v == null || v === 0 ? undefined : v > 0 ? "pos" : "neg");

/** Seconds to m:ss. */
export function toi(sec: N) {
  if (!sec) return DASH;
  const m = Math.floor(sec / 60), s = Math.round(sec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}
/** Seconds to whole minutes. */
export const toiMin = (sec: N) => (sec ? (sec / 60).toFixed(0) : DASH);
export const per60 = (x: number, sec: N) => (sec ? (x * 3600) / sec : null);
export const share = (f: number, a: number) => (f + a > 0 ? f / (f + a) : null);

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** 2026-10-19 to "Oct 19". */
export function fmtDate(d: string) {
  const [, m, dd] = d.split("-");
  return `${MONTHS[+m - 1]} ${+dd}`;
}
/** 2026-10-19 to "Monday, October 19". Fixed locale so builds are stable. */
export const longDate = (d: string) =>
  new Date(d + "T12:00:00Z").toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", timeZone: "UTC" });

/** 2026 to "2026-27". */
export const seasonLabel = (s: number) => `${s}-${String((s + 1) % 100).padStart(2, "0")}`;

/** Period number to "1st" … "OT", "2OT". */
export const ORD = (p: number) => (p <= 3 ? ["1st", "2nd", "3rd"][p - 1] : p === 4 ? "OT" : `${p - 3}OT`);

/** 1 to "1st", 22 to "22nd". */
export const ordinal = (k: number) =>
  k + ["th", "st", "nd", "rd"][k % 100 > 10 && k % 100 < 14 ? 0 : k % 10 < 4 ? k % 10 : 0];
