// A full NHL rink in feet, centre ice at the origin: x from -100 to 100,
// y from -42.5 to 42.5. Shots are drawn in the same coordinates.

const GOAL_X = 89, R_CREASE = 6;
export const RINK_PATH =
  "M -72 -42.5 H 72 A 28 28 0 0 1 100 -14.5 V 14.5 A 28 28 0 0 1 72 42.5 H -72 A 28 28 0 0 1 -100 14.5 V -14.5 A 28 28 0 0 1 -72 -42.5 Z";

/** Board, lines, creases and dots. Place inside an <svg viewBox="-102 -45 204 90">. */
export function RinkMarks({ id = "ice" }: { id?: string }) {
  const paint = { fill: "none", stroke: "var(--paint)", strokeWidth: 0.35 };
  const red = { fill: "none", stroke: "var(--rink-red)", strokeWidth: 0.6 };
  return (
    <>
      <clipPath id={id}><path d={RINK_PATH} /></clipPath>
      <path d={RINK_PATH} fill="var(--ice)" stroke="var(--board)" strokeWidth={0.7} />
      <g clipPath={`url(#${id})`}>
        <line x1={0} y1={-42.5} x2={0} y2={42.5} {...red} strokeWidth={1.1} />
        {[-25, 25].map(x => <line key={x} x1={x} y1={-42.5} x2={x} y2={42.5} fill="none" stroke="var(--rink-blue)" strokeWidth={1.1} />)}
        {[-1, 1].map(s => {
          const gx = s * GOAL_X, cx = s * (GOAL_X - Math.sqrt(R_CREASE * R_CREASE - 16));
          return (
            <g key={s}>
              <line x1={gx} y1={-36.75} x2={gx} y2={36.75} {...red} />
              <path d={`M ${gx} -4 H ${cx.toFixed(2)} A ${R_CREASE} ${R_CREASE} 0 0 ${s > 0 ? 0 : 1} ${cx.toFixed(2)} 4 H ${gx}`} {...red} />
              <rect x={s > 0 ? gx : gx - 4} y={-3} width={4} height={6} {...red} />
              {[[69, -22], [69, 22]].map(([x, y]) => (
                <g key={y}>
                  <circle cx={s * x} cy={y} r={15} {...paint} />
                  <circle cx={s * x} cy={y} r={1} fill="var(--rink-red)" />
                </g>
              ))}
              {[[20, -22], [20, 22]].map(([x, y]) => <circle key={y} cx={s * x} cy={y} r={1} fill="var(--rink-red)" />)}
            </g>
          );
        })}
        <circle cx={0} cy={0} r={15} fill="none" stroke="var(--rink-blue)" strokeWidth={0.5} />
      </g>
    </>
  );
}

/** Dot radius for a shot's xG: area grows with probability. */
export const shotRadius = (xg: number) => 1.1 + Math.sqrt(Math.max(xg, 0)) * 5.5;
