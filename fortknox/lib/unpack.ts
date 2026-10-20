import type { RawSheet, Sheet, Shot } from "./types";

/** Unpack a published sheet's shot rows (keyed by shot_keys) into objects.
 *  Pages hand the compact rows to the browser and unpack them there. */
export function unpack(raw: RawSheet): Sheet {
  const { shot_keys, shots, ...rest } = raw;
  return {
    ...rest,
    shots: shots.map((r, i) => {
      const o = Object.fromEntries(shot_keys.map((k, j) => [k, r[j]])) as unknown as Shot;
      o.i = i;
      return o;
    }),
  };
}
