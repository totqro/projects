#!/usr/bin/env python3
"""
Score a hand-tagged shot chart with the saved xG model.

    python score_tagged.py shots.csv               # per-shot xG + game totals
    python score_tagged.py shots.csv --out xg.csv  # also write the scored rows
    python score_tagged.py shots.csv --tier HIGH   # only the HIGH-danger zone

Input is the x/y export from the shot-scatter tagger:

    Period,Team,Player,Type,X,Y,Shot Type,Strength

X/Y are raw NHL rink feet (x -100..100, y -42.5..42.5), so shots at the left
end are mirrored onto the attacking-right frame the model was trained in
(net at x = +89) before anything is computed.

Type is Shot/Goal/Miss/Block. Only BLOCKED shots are dropped: the model is fit
on unblocked attempts, 30% of which (269,893 of 905,483) are misses carrying
goal=0, so throwing misses away would undercount a game's xG. Blocks are the
one category MoneyPuck itself excludes (see clean.py, valid_event).

Shot-type words are mapped onto the model's vocabulary, and anything without a
match (Scramble, blanks) is scored as UNKNOWN rather than guessed at. UNKNOWN
is not a null: it is the NHL's own unrecorded-type bucket, which is mostly
crease chaos — 42% rebounds at a median 9 ft — and the model gives it a real
coefficient. What a scramble tag cannot supply is the rebound flag, which is
where most of that danger actually lives.
"""

import argparse
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from xg_model import FEATURES, MODEL_PATH, predict_xg
from zone_tagging import GOAL_X, ZONE16_NAMES, geometry, zone16

# Tagger vocabulary -> the model's. Left off deliberately: Scramble and
# anything blank, which have no NHL shotType equivalent -> UNKNOWN.
SHOT_TYPES = {
    "wrist shot": "WRIST", "wrist": "WRIST",
    "snap shot": "SNAP", "snap": "SNAP",
    "slap shot": "SLAP", "slap": "SLAP",
    "backhand": "BACK", "back": "BACK",
    "tip-in": "TIP", "tip in": "TIP", "tip": "TIP", "redirect": "TIP",
    "deflected": "DEFL", "deflection": "DEFL",
    "wrap-around": "WRAP", "wrap around": "WRAP", "wraparound": "WRAP",
}
SITUATIONS = {
    "5v5": "EV_5v5", "4v4": "EV_4v4", "3v3": "EV_3v3",
    "5v4": "PP_5v4", "5v3": "PP_5v3", "4v3": "PP_4v3",
    "4v5": "SH_4v5", "3v5": "SH_OTHER", "3v4": "SH_OTHER",
    "6v5": "EN_6v5_PULLED", "5v6": "EN_AGAINST",
}
GOAL_WORDS = {"goal"}
# The model's population is unblocked attempts, misses included.
UNBLOCKED = {"shot", "goal", "save", "shot on goal", "miss", "missed",
             "missed shot", "wide", "post", "crossbar"}
BLOCKED = {"block", "blocked", "blocked shot"}

# The tagger's tiers, for the zone read (see web/index.html).
TIER = {5: "HIGH", 8: "HIGH", 4: "MED", 6: "MED", 10: "MED", 11: "MED",
        12: "MED"}


def load_tagged(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    need = {"period", "team", "type", "x", "y", "shot_type", "strength"}
    missing = need - set(df.columns)
    if missing:
        sys.exit(f"{path.name}: missing column(s) {sorted(missing)}")

    out = pd.DataFrame(index=df.index)
    out["period"] = df["period"]
    out["team"] = df["team"].astype(str).str.strip()
    out["player"] = df.get("player", pd.Series("", index=df.index)).fillna("")
    out["event"] = df["type"].astype(str).str.strip().str.lower()

    # Mirror the left end onto the attacking-right frame. Flipping x has to
    # flip y with it or every left-end shot lands on the wrong wing.
    x, y = df["x"].astype(float), df["y"].astype(float)
    flip = x < 0
    out["x_adj"] = np.where(flip, -x, x)
    out["y_adj"] = np.where(flip, -y, y)
    out["mirrored"] = flip.astype(int)

    d, a = geometry(out["x_adj"], out["y_adj"])
    out["distance"] = d
    out["angle_from_net"] = a
    out["zone"] = zone16(out["x_adj"], out["y_adj"], numbered=True)
    out["zone_name"] = [ZONE16_NAMES[z] for z in out["zone"]]
    out["tier"] = [TIER.get(z, "LOW") for z in out["zone"]]

    raw_type = df["shot_type"].fillna("").astype(str).str.strip().str.lower()
    out["shot_type"] = raw_type.map(SHOT_TYPES).fillna("UNKNOWN")
    out["tagged_type"] = df["shot_type"].fillna("").astype(str).str.strip()

    raw_str = df["strength"].fillna("").astype(str).str.strip().str.lower()
    out["situation"] = raw_str.map(SITUATIONS).fillna("EV_5v5")
    out["tagged_strength"] = df["strength"].fillna("").astype(str).str.strip()

    # The tagger has no timestamps, so rebounds cannot be derived. A rebound
    # column is honoured if the tagger ever grows one; otherwise 0.
    out["is_rebound"] = (
        df["rebound"].fillna(0).astype(int) if "rebound" in df.columns
        else 0
    )
    out["goal"] = out["event"].isin(GOAL_WORDS).astype(int)
    out["scored"] = out["event"].isin(UNBLOCKED)
    out["blocked"] = out["event"].isin(BLOCKED)
    return out


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", type=Path)
    ap.add_argument("--out", type=Path, help="write the scored rows here")
    ap.add_argument("--tier", choices=["HIGH", "MED", "LOW"],
                    help="only shots in this danger tier (see web/index.html)")
    args = ap.parse_args()

    if not MODEL_PATH.exists():
        sys.exit("No saved model. Run `python xg_model.py` first.")
    model = joblib.load(MODEL_PATH)

    df = load_tagged(args.csv)
    scored = df[df.scored].copy()
    blocked = int(df.blocked.sum())
    unrecognised = df[~df.scored & ~df.blocked]
    scored["xg"] = predict_xg(model, scored)

    label = f"{args.csv.name}: {len(df)} tagged events, {len(scored)} scored"
    if blocked:
        label += f", {blocked} blocked (dropped)"
    if len(unrecognised):
        kinds = ", ".join(sorted(set(unrecognised.event.replace("", "(blank)"))))
        label += f", {len(unrecognised)} unrecognised type ({kinds}, dropped)"
    if args.tier:
        before = len(scored)
        scored = scored[scored.tier == args.tier]
        label += f"; {args.tier} only: {len(scored)}/{before}"
    print(label)

    if scored.empty:
        return

    print("\nPer shot")
    print(f"  {'P':>2} {'team':<6}{'tier':<5}{'zone':<14}{'dist':>6}{'ang':>5}  "
          f"{'type':<8}{'situation':<10}{'':<5}{'xG':>7}")
    order = {"HIGH": 0, "MED": 1, "LOW": 2}
    for _, s in scored.sort_values(
            by="tier", key=lambda c: c.map(order)).iterrows():
        mark = "GOAL" if s.goal else ""
        print(f"  {s.period:>2} {s.team:<6}{s.tier:<5}{s.zone_name:<14}"
              f"{s.distance:>6.1f}{s.angle_from_net:>5.0f}  {s.shot_type:<8}"
              f"{s.situation:<10}{mark:<5}{s.xg:>7.3f}")

    print("\nTotals")
    print(f"  {'team':<8}{'shots':>7}{'goals':>7}{'xG':>8}{'G-xG':>8}"
          f"{'xG/shot':>9}")
    for team, g in scored.groupby("team"):
        print(f"  {team:<8}{len(g):>7}{int(g.goal.sum()):>7}{g.xg.sum():>8.2f}"
              f"{g.goal.sum()-g.xg.sum():>+8.2f}{g.xg.mean():>9.3f}")

    if not args.tier:
        print("\nShot quality mix")
        for team, g in scored.groupby("team"):
            parts = [f"{t} {(g.tier==t).mean()*100:.0f}%" for t in
                     ("HIGH", "MED", "LOW")]
            print(f"  {team:<8}{'  '.join(parts)}")

    unknown = (scored.shot_type == "UNKNOWN")
    if unknown.any():
        kinds = scored.loc[unknown, "tagged_type"].replace("", "(blank)")
        print(f"\n  note: {unknown.sum()} shot(s) scored as UNKNOWN type "
              f"({', '.join(sorted(set(kinds)))}) — the NHL's own unrecorded "
              f"bucket, mostly crease chaos. Tag them as rebounds if they were.")
    if scored.mirrored.any():
        print(f"  note: {int(scored.mirrored.sum())} shot(s) had x < 0 and "
              f"were mirrored onto the attacking-right frame.")
    if not scored.is_rebound.any():
        print("  note: no rebound flags — the export has no timestamps, so "
              "rebounds cannot be derived. Rebound shots score low here.")

    if args.out:
        cols = ["period", "team", "player", "event", "x_adj", "y_adj",
                "distance", "angle_from_net", "zone", "zone_name", "tier",
                *FEATURES, "goal", "xg"]
        scored[cols].to_csv(args.out, index=False)
        print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
