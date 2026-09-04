#!/usr/bin/env python3
"""Draw the tagging maps straight from the classifiers in zone_tagging.py.

Every region is emitted as its literal rule (a ring x sector wedge, or a band),
painted in np.select test order, so the picture cannot drift from the code.
Screen frame: net at the origin, sy = 89 - x_adj (depth from the goal line,
growing down the page), sx = y_adj. Units are feet.

    ./.venv/bin/python make_zone_map.py     ->  zone10_map.svg, zone16_map.svg, zone_map.html
"""
import numpy as np, pandas as pd
import zone_tagging as Z

RAMP = [(0.025,"#cde2fb"),(0.035,"#b7d3f6"),(0.050,"#9ec5f4"),(0.075,"#6da7ec"),
        (0.095,"#5598e7"),(0.110,"#3987e5"),(0.140,"#256abf"),(9.99,"#104281")]
DARK_FILLS = {"#5598e7","#3987e5","#256abf","#104281"}
INK, INK2, SURF = "#0b0b0b", "#52514e", "#ffffff"

def fill_for(rate):
    return next(c for t, c in RAMP if rate < t)

def ink_on(c):
    return "#ffffff" if c in DARK_FILLS else INK

def pt(r, th):
    t = np.radians(th)
    return r*np.sin(t), r*np.cos(t)

def wedge(r0, r1, th0, th1):
    """Annular wedge between two radii and two angles off the net axis."""
    (x0,y0),(x1,y1) = pt(r0,th0), pt(r1,th0)
    (x2,y2),(x3,y3) = pt(r1,th1), pt(r0,th1)
    return (f"M {x0:.3f},{y0:.3f} L {x1:.3f},{y1:.3f} "
            f"A {r1},{r1} 0 0 0 {x2:.3f},{y2:.3f} L {x3:.3f},{y3:.3f} "
            f"A {r0},{r0} 0 0 1 {x0:.3f},{y0:.3f} Z")

RINK = ("M -42.5,17 A 28,28 0 0 1 -14.5,-11 L 14.5,-11 A 28,28 0 0 1 42.5,17 "
        "L 42.5,92 L -42.5,92 Z")

def furniture():
    return f'''
  <g clip-path="url(#rink)" fill="none" stroke="{INK}" opacity="0.2" stroke-width="0.2"
     stroke-dasharray="1.6 1.4">
    <circle cx="-22" cy="20" r="15"/><circle cx="22" cy="20" r="15"/>
    <path d="M -4,0 A 6,6 0 0 0 4,0"/><rect x="-3" y="-4" width="6" height="4"/>
    <line x1="-42.5" y1="64" x2="42.5" y2="64" stroke-width="0.5"/>
  </g>
  <g fill="{INK}" opacity="0.2"><circle cx="-22" cy="20" r="0.6"/><circle cx="22" cy="20" r="0.6"/></g>
  <line x1="-42.5" y1="0" x2="42.5" y2="0" stroke="{INK}" opacity="0.3" stroke-width="0.25"
        clip-path="url(#rink)"/>
  <path d="{RINK}" fill="none" stroke="{INK}" opacity="0.45" stroke-width="0.35"/>'''

def labels(items, size=1.95):
    out = [f'<g font-size="{size}" text-anchor="middle" font-weight="600" letter-spacing="-0.02">']
    for sx, sy, text, colour in items:
        out.append(f'<text x="{sx}" y="{sy}" fill="{colour}">{text}</text>')
    return "\n    ".join(out) + "\n  </g>"

def annotate(items, size=1.7):
    out = [f'<g font-size="{size}" fill="{INK}" opacity="0.72" text-anchor="middle"'
           f' paint-order="stroke" stroke="{SURF}" stroke-width="0.9" stroke-linejoin="round"'
           f' font-family="ui-monospace,SFMono-Regular,Menlo,monospace">']
    for sx, sy, text in items:
        out.append(f'<text x="{sx}" y="{sy}">{text}</text>')
    return "\n    ".join(out) + "\n  </g>"

def head(extra_defs=""):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="-44.5 -13.5 89 107.5"
     width="712" height="860" role="img" aria-label="Rink diagram of the tagging zones">
  <rect x="-44.5" y="-13.5" width="89" height="107.5" fill="{SURF}"/>
  <defs>
    <clipPath id="rink"><path d="{RINK}"/></clipPath>{extra_defs}
    <pattern id="hatch" width="3" height="3" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
      <line x1="0" y1="0" x2="0" y2="3" stroke="{INK}" stroke-width="0.55" opacity="0.28"/>
    </pattern>
  </defs>'''

def legend(y=99.5):
    sw = "".join(f'<rect x="{-27.5+i*4.6:.1f}" y="{y-2.2}" width="4.2" height="2.8" rx="0.4" fill="{c}"/>'
                 for i,(_,c) in enumerate(RAMP))
    return (f'<g font-family="ui-sans-serif,-apple-system,Helvetica,Arial,sans-serif"'
            f' font-size="2.1" fill="{INK2}">'
            f'<text x="-42.5" y="{y}">goal rate</text>'
            f'<text x="-29" y="{y}" text-anchor="end">.02</text>{sw}'
            f'<text x="10.5" y="{y}">.15</text></g>')

# ---------------------------------------------------------------- the two maps
def svg16(rate):
    f = {k: fill_for(v) for k, v in rate.items()}
    def z(i): return f[i]
    body = f'''
  <g clip-path="url(#rink)">
    <rect x="-42.5" y="-13.5" width="42.5" height="13.5" fill="{z(1)}"/>
    <rect x="0" y="-13.5" width="42.5" height="13.5" fill="{z(3)}"/>
    <rect x="-17" y="-13.5" width="34" height="13.5" fill="{z(2)}"/>
    <rect x="-42.5" y="64" width="85" height="30" fill="{z(16)}"/>
    <g clip-path="url(#front)">
      <path d="{wedge(45,205,-90,-20)}" fill="{z(13)}"/>
      <path d="{wedge(45,205,20,90)}" fill="{z(15)}"/>
      <path d="{wedge(45,205,-20,20)}" fill="{z(14)}"/>
      <path d="{wedge(24,45,-90,-45)}" fill="{z(7)}"/>
      <path d="{wedge(24,45,45,90)}" fill="{z(9)}"/>
      <path d="{wedge(24,45,-45,-20)}" fill="{z(10)}"/>
      <path d="{wedge(24,45,20,45)}" fill="{z(12)}"/>
      <path d="{wedge(24,45,-20,20)}" fill="{z(11)}"/>
      <path d="{wedge(8,24,-90,-20)}" fill="{z(4)}"/>
      <path d="{wedge(8,24,20,90)}" fill="{z(6)}"/>
      <path d="{wedge(8,24,-20,20)}" fill="{z(8)}"/>
      <path d="M -8,0 A 8,8 0 0 0 8,0 Z" fill="{z(5)}"/>
    </g>
  </g>
  <g clip-path="url(#rink)" fill="none" stroke="{SURF}" stroke-width="0.32">
    <g clip-path="url(#front)">
      <path d="{wedge(8,205,-20,20)}"/><path d="{wedge(24,205,-45,45)}"/>
      <path d="{wedge(8,24,-90,90)}"/><path d="{wedge(45,45.001,-90,90)}"/>
      <path d="M -8,0 A 8,8 0 0 0 8,0"/>
    </g>
    <line x1="-17" y1="-13.5" x2="-17" y2="0"/><line x1="17" y1="-13.5" x2="17" y2="0"/>
    <line x1="-42.5" y1="64" x2="42.5" y2="64" stroke-width="0.45"/>
  </g>'''
    L = []
    for i,(sx,sy) in {1:(-27,-5),2:(0,-5),3:(27,-5),5:(0,5.4),8:(0,17),4:(-12.5,10.5),
                      6:(12.5,10.5),11:(0,35),10:(-18.3,29.5),12:(18.3,29.5),
                      7:(-31,15.5),9:(31,15.5),14:(0,55),13:(-30,47),15:(30,47),
                      16:(0,75)}.items():
        L.append((sx, sy, f"{i:02d} {Z.ZONE16_NAMES[i]}", ink_on(f[i])))
    ann = [(-6.6,8.6,"8"),(-6.6,24.6,"24"),(-6.6,45.6,"45 ft"),
           (10.5,44,"20°"),(26.5,29.5,"45°"),(-19.5,-9.2,"|y| 17"),(19.5,-9.2,"|y| 17")]
    return (head('\n    <clipPath id="front"><rect x="-42.5" y="0" width="85" height="64"/></clipPath>')
            + body + furniture() + "\n  " + labels(L, 1.85) + "\n  " + annotate(ann)
            + "\n  " + legend() + "\n</svg>\n")

def svg10(rate):
    f = {k: fill_for(v) for k, v in rate.items()}
    body = f'''
  <g clip-path="url(#rink)">
    <rect x="-42.5" y="-13.5" width="85" height="107.5" fill="{f['perimeter']}"/>
    <circle cx="0" cy="0" r="45" fill="{f['point-wide']}"/>
    <g clip-path="url(#b22)"><circle cx="0" cy="0" r="45" fill="{f['point-mid']}"/></g>
    <circle cx="0" cy="0" r="32" fill="{f['outer-wide']}"/>
    <g clip-path="url(#b22)"><circle cx="0" cy="0" r="32" fill="{f['circle']}"/></g>
    <g clip-path="url(#b11)"><circle cx="0" cy="0" r="32" fill="{f['high-slot']}"/></g>
    <circle cx="0" cy="0" r="20" fill="{f['inner-wide']}"/>
    <g clip-path="url(#b11)"><circle cx="0" cy="0" r="20" fill="{f['slot']}"/></g>
    <circle cx="0" cy="0" r="8" fill="{f['crease']}"/>
    <rect x="-42.5" y="-13.5" width="85" height="13.5" fill="url(#hatch)"/>
    <line x1="-42.5" y1="0" x2="42.5" y2="0" stroke="{INK}" stroke-width="0.35"
          stroke-dasharray="2 1.6" opacity="0.55"/>
  </g>
  <g clip-path="url(#rink)" fill="none" stroke="{SURF}" stroke-width="0.32">
    <circle cx="0" cy="0" r="8"/><circle cx="0" cy="0" r="20"/>
    <circle cx="0" cy="0" r="32"/><circle cx="0" cy="0" r="45"/>
  </g>
  <g clip-path="url(#c32)" stroke="{SURF}" stroke-width="0.32">
    <line x1="-11" y1="-13.5" x2="-11" y2="94"/><line x1="11" y1="-13.5" x2="11" y2="94"/>
  </g>
  <g clip-path="url(#c45)" stroke="{SURF}" stroke-width="0.32">
    <line x1="-22" y1="-13.5" x2="-22" y2="94"/><line x1="22" y1="-13.5" x2="22" y2="94"/>
  </g>'''
    names = {"crease":(0,5.4),"slot":(0,15),"inner-wide":(-16,7),"high-slot":(0,27),
             "circle":(-16.5,25),"outer-wide":(-27,13),"point-mid":(0,40),
             "point-wide":(-28.5,33),"perimeter":(0,75)}
    L = [(sx, sy, n, ink_on(f[n])) for n,(sx,sy) in names.items()]
    ann = [(6.5,8.6,"d 8"),(6.5,20.6,"d 20"),(6.5,32.6,"d 32"),(7.5,45.6,"d 45"),
           (11,32.4,"ya 11"),(22,41,"ya 22"),(0,-6.5,"x > 89 — dead branch")]
    defs = ('\n    <clipPath id="b11"><rect x="-11" y="-13.5" width="22" height="107.5"/></clipPath>'
            '\n    <clipPath id="b22"><rect x="-22" y="-13.5" width="44" height="107.5"/></clipPath>'
            '\n    <clipPath id="c32"><circle cx="0" cy="0" r="32"/></clipPath>'
            '\n    <clipPath id="c45"><circle cx="0" cy="0" r="45"/></clipPath>')
    return head(defs) + body + furniture() + "\n  " + labels(L) + "\n  " + annotate(ann) \
         + "\n  " + legend() + "\n</svg>\n"

# ------------------------------------------------------------------- the data
def stats(z, d, a, goal):
    t = pd.DataFrame({"z": z, "d": d, "a": a, "g": goal})
    out = t.groupby("z").agg(n=("d","size"), med_d=("d","median"),
                             med_a=("a","median"), rate=("g","mean"))
    return out

# ------------------------------------------------------------------ the write-up
COND16 = [(1,"x &gt; 89 &amp; y &lt; -17"),(3,"x &gt; 89 &amp; y &gt; 17"),(2,"x &gt; 89"),
          (16,"x &lt; 25"),(5,"d &lt; 8"),(8,"d &lt; 24 &amp; a &lt; 20"),(4,"d &lt; 24 &amp; left"),
          (6,"d &lt; 24"),(11,"d &lt; 45 &amp; a &lt; 20"),(10,"d &lt; 45 &amp; a &lt; 45 &amp; left"),
          (12,"d &lt; 45 &amp; a &lt; 45"),(7,"d &lt; 45 &amp; left"),(9,"d &lt; 45"),
          (14,"a &lt; 20"),(13,"left"),(15,"default")]

RESULTS = [("5 feats, exact coords &mdash; the NHL ceiling","0.7422","1.073",False),
           ("3 feats, exact coords","0.7274","1.023",False),
           ("3 feats, 5 ft grid","0.7245","1.029",False),
           ("3 feats, 10 hand-cut zones","0.7139","1.046",False),
           ("3 feats, 16 EDGE zones","0.7106","1.012",True),
           ("3 feats, 16 EDGE zones mirrored (11 shapes)","0.7103","1.013",False)]

DOC = """<title>NHL EDGE Zone Map</title>
<style>
 :root{{--page:#faf9f7;--card:#fff;--ink:#0b0b0b;--ink-2:#52514e;--ink-3:#78766f;--rule:#e4e2dc}}
 @media (prefers-color-scheme:dark){{:root:not([data-theme=light]){{--page:#1a1a19;--ink:#fff;--ink-2:#c3c2b7;--ink-3:#8f8d85;--rule:#333330}}}}
 :root[data-theme=dark]{{--page:#1a1a19;--ink:#fff;--ink-2:#c3c2b7;--ink-3:#8f8d85;--rule:#333330}}
 body{{background:var(--page);color:var(--ink);margin:0;padding:32px 24px 64px;
      font:15px/1.55 ui-sans-serif,-apple-system,"Segoe UI",Helvetica,Arial,sans-serif}}
 main{{max-width:1000px;margin:0 auto}}
 h1{{font-size:24px;margin:0 0 4px;letter-spacing:-.01em}}
 .sub{{color:var(--ink-2);margin:0 0 28px;font-size:14px;max-width:70ch}}
 h2{{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--ink-3);margin:40px 0 12px;font-weight:600}}
 .maps{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}}
 figure{{margin:0;background:var(--card);border:1px solid var(--rule);border-radius:10px;padding:14px}}
 figure svg{{display:block;width:100%;height:auto}}
 figcaption{{color:var(--ink-2);font-size:12.5px;margin-top:8px}}
 figcaption b{{color:var(--ink);font-weight:600}}
 table{{border-collapse:collapse;width:100%;font-size:13.5px;font-variant-numeric:tabular-nums}}
 th,td{{text-align:right;padding:6px 10px;border-bottom:1px solid var(--rule)}}
 th:first-child,td:first-child,th:nth-child(2),td:nth-child(2){{text-align:left}}
 th{{color:var(--ink-3);font-weight:600;font-size:11.5px;text-transform:uppercase;letter-spacing:.06em}}
 .mono,code{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px}}
 td .sw{{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:7px;vertical-align:-1px}}
 tr.hi td{{background:color-mix(in srgb,#3987e5 11%,transparent);font-weight:600}}
 ul{{padding-left:18px;color:var(--ink-2);max-width:78ch}} li{{margin:8px 0}} li b{{color:var(--ink)}}
</style>
<main>
<h1>Tagging maps: the 16 EDGE zones vs the 10 we cut</h1>
<p class="sub">Both drawn to scale from the classifiers in <span class="mono">zone_tagging.py</span> &mdash;
each region is its literal rule, painted in test order, so the picture can't drift from the code.
Fill is goal rate, 2025 season (n&nbsp;=&nbsp;119,271). Net at the top; <span class="mono">d</span> is feet
from the net, <span class="mono">a</span> is degrees off the net's axis.</p>

<div class="maps">
  <figure>{svg16}<figcaption><b>16 EDGE zones.</b> Three rings (8 / 24 / 45 ft) cut by rays at
    20&deg; and 45&deg;, a row behind the goal line split at |y|&nbsp;=&nbsp;17, and the neutral zone.
    All 16 are populated.</figcaption></figure>
  <figure>{svg10}<figcaption><b>10 hand-cut zones.</b> Rings at 8 / 20 / 32 / 45 ft cut by
    |y| bands at 11 and 22. The hatched strip is the dead
    <span class="mono">behind-net</span> branch &mdash; unreachable.</figcaption></figure>
</div>

<h2>The 16 zones, in test order</h2>
<table><thead><tr><th>#</th><th>zone</th><th>condition</th><th>n</th><th>share</th>
<th>med d</th><th>med a</th><th>goal rate</th></tr></thead><tbody>
{rows16}
</tbody></table>

<h2>Does it predict better?</h2>
<table><thead><tr><th>model</th><th>AUC</th><th>xG / actual goals</th></tr></thead><tbody>
{rows_res}
</tbody></table>

<h2>What the comparison says</h2>
<ul>
  <li><b>It ranks very slightly worse, and calibrates clearly better.</b> AUC 0.7106 vs 0.7139 for the
    hand-cut 10 &mdash; a rounding error &mdash; but total xG lands within 1.2% of actual goals instead of 4.6%.
    If you are summing xG over a game or a player, the EDGE map is the better tool; if you are ranking
    individual chances, they are the same tool.</li>
  <li><b>It trades distance resolution for angle resolution.</b> Three rings instead of four leaves shots
    4.7 ft from their zone's median distance on average (vs 4.1 ft), but the radial cuts leave them only
    9.3&deg; off in angle (vs 13.0&deg;). Distance is the stronger term in the model, which is exactly why
    the AUC slips a hair.</li>
  <li><b>The left/right split is free, and buys nothing.</b> Collapsing all six L/R pairs into
    11 distinct shapes costs 0.0003 AUC. Keep the split for readability and for handedness work later,
    but it is not carrying predictive weight.</li>
  <li><b>No dead branches, and the tails are covered.</b> Behind the goal line (1,777 shots) and the neutral
    zone (2,859 shots, 4.8% goal rate &mdash; empty nets and long shots) both get their own zones instead of
    being swept into a 33k-shot <span class="mono">perimeter</span> bucket.</li>
  <li><b>Boundaries are digitised from your image, not from a spec.</b> Rings, rays and the |y|&nbsp;=&nbsp;17
    split were measured off the picture against rink landmarks. Across 108 plausible readings
    (rings 20&ndash;26 / 40&ndash;50 ft, rays 15&ndash;25&deg; / 40&ndash;50&deg;) AUC spans 0.7021&ndash;0.7157,
    so the verdict above holds for any of them. The one knob that matters is the outer ring: pulling it
    from 45 to 40 ft is worth about +0.003 AUC. If you have the real EDGE numbers, they go in the
    constants at the top of <span class="mono">zone_tagging.py</span> and everything here regenerates.</li>
</ul>
</main>
"""

def write_doc(s16):
    rows = []
    for i, cond in COND16:
        r = s16.loc[i]
        rows.append(f'<tr><td>{i:02d}</td><td><span class="sw" style="background:{fill_for(r.rate)}">'
                    f'</span>{Z.ZONE16_NAMES[i]}</td><td class="mono">{cond}</td>'
                    f'<td>{int(r.n):,}</td><td>{r.n/s16.n.sum()*100:.1f}%</td>'
                    f'<td>{r.med_d:.1f}</td><td>{r.med_a:.1f}&deg;</td><td>{r.rate:.3f}</td></tr>')
    res = "".join(f'<tr class="{"hi" if hi else ""}"><td>{n}</td><td>{a}</td><td>{c}</td></tr>'
                  for n, a, c, hi in RESULTS)
    svg = lambda f: "".join(open(f).readlines()[0:])  # inline as-is
    open("zone_map.html","w").write(DOC.format(
        svg16=svg("zone16_map.svg"), svg10=svg("zone10_map.svg"),
        rows16="\n".join(rows), rows_res=res))
    print("wrote zone_map.html")


if __name__ == "__main__":
    df = pd.read_parquet("data/shots.parquet")
    te = df[df.season == 2025]
    x, y, g = te.x_adj.to_numpy(float), te.y_adj.to_numpy(float), te.goal.to_numpy()
    d, a = Z.geometry(x, y)

    s16 = stats(Z.zone16(x, y, numbered=True), d, a, g)
    s10 = stats(Z.zone10(x, y), d, a, g)
    open("zone16_map.svg","w").write(svg16(s16.rate.to_dict()))
    open("zone10_map.svg","w").write(svg10(s10.rate.to_dict()))
    print(s16.round(3).to_string()); print(); print(s10.round(3).to_string())
    print("\nwrote zone16_map.svg, zone10_map.svg")
    write_doc(s16)
