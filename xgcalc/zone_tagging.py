#!/usr/bin/env python3
"""Zone tagging schemes for shots you can only eyeball off a VOD.

Two schemes, both in the attacking-right frame (net at (GOAL_X, 0)):

  zone10  the polar rings x |y| bands we cut by hand
  zone16  the NHL EDGE style 16-region map: three rows in front of the net,
          a row behind the goal line, and the neutral zone

Both take x_adj / y_adj arrays and return a string array. Every boundary is a
named constant so the map can be retuned without hunting through np.select.
"""
import numpy as np

GOAL_X = 89.0

# --- zone16 geometry ---------------------------------------------------------
R_CREASE, R_MID, R_FAR = 8.0, 24.0, 45.0   # rings, ft from the net
A_SLOT, A_WIDE = 20.0, 45.0                # radial cuts, deg off the net axis
Y_BEHIND = 17.0                            # 1|2|3 split behind the goal line
BLUE_LINE_X = 25.0                         # everything past it is one zone

ZONE16_NAMES = {
     1: "L corner",   2: "behind net",  3: "R corner",
     4: "L post",     5: "crease",      6: "R post",
     7: "L boards",   8: "inner slot",  9: "R boards",
    10: "L circle",  11: "slot",       12: "R circle",
    13: "L point",   14: "mid point",  15: "R point",
    16: "neutral zone",
}


def geometry(x, y):
    """(distance, angle) to the net. Angle is degrees off the net's axis, so
    anything behind the goal line comes back > 90."""
    x = np.asarray(x, dtype=float); y = np.asarray(y, dtype=float)
    dx = GOAL_X - x; ya = np.abs(y)
    return np.hypot(dx, ya), np.degrees(np.arctan2(ya, dx))


def zone10(x, y):
    """The hand-cut scheme: rings at 8/20/32/45 ft x |y| bands at 11/22 ft."""
    x = np.asarray(x, dtype=float); y = np.asarray(y, dtype=float)
    d, _ = geometry(x, y); ya = np.abs(y)
    return np.select(
        [ d < 8,
          (d < 20) & (ya < 11), (d < 20),
          (d < 32) & (ya < 11), (d < 32) & (ya < 22), (d < 32),
          (d < 45) & (ya < 22), (d < 45),
          x > GOAL_X ],
        ["crease", "slot", "inner-wide", "high-slot", "circle", "outer-wide",
         "point-mid", "point-wide", "behind-net"],
        default="perimeter")


def zone16(x, y, numbered=False):
    """NHL EDGE style 16 zones. Tested in order, first match wins."""
    x = np.asarray(x, dtype=float); y = np.asarray(y, dtype=float)
    d, a = geometry(x, y)
    left = y < 0
    behind, neutral = x > GOAL_X, x < BLUE_LINE_X
    n = np.select(
        [ behind & (y < -Y_BEHIND), behind & (y > Y_BEHIND), behind,
          neutral,
          d < R_CREASE,
          (d < R_MID) & (a < A_SLOT), (d < R_MID) & left, d < R_MID,
          (d < R_FAR) & (a < A_SLOT),
          (d < R_FAR) & (a < A_WIDE) & left, (d < R_FAR) & (a < A_WIDE),
          (d < R_FAR) & left, d < R_FAR,
          a < A_SLOT, left ],
        [1, 3, 2,
         16,
         5,
         8, 4, 6,
         11,
         10, 12,
         7, 9,
         14, 13],
        default=15)
    if numbered:
        return n
    return np.array([f"{i:02d} {ZONE16_NAMES[i]}" for i in n])


def mirror16(z):
    """Collapse the left/right pairs -> the 9 distinct shapes."""
    return np.array([s.split(" ", 1)[1].replace("L ", "").replace("R ", "") for s in z])


# --- coaching danger tiers ----------------------------------------------------
# The coaches' map, attacking frame. A label for reports, never a model input:
# the model already prices location, rush and royal-road passes.
#
#   HIGH    the box from the goal line to the faceoff-dot line, |y| <= 11
#   MEDIUM  a trapezoid from that box's edges at the goal line out to the dots
#           (|y| = 22) at the dot line, then |y| <= 22 out to the circle tops
#   LOW     everything else, behind the net included
#
# Overrides, in order: an odd-man rush moves up one tier, a royal-road pass
# makes it HIGH, and a blocked attempt then drops one tier (never below LOW).
DOT_X = 69.0               # faceoff dots
CIRCLE_TOP_X = 54.0        # dots minus the 15 ft circle radius
HIGH_Y, DOT_Y = 11.0, 22.0
TIERS = ("LOW", "MEDIUM", "HIGH")


def danger_tier(x, y, rush=0, royal_road=0, blocked=0):
    """'HIGH' / 'MEDIUM' / 'LOW' per shot. Arrays in, string array out."""
    x = np.asarray(x, dtype=float); ya = np.abs(np.asarray(y, dtype=float))
    in_front = x <= GOAL_X
    deep = in_front & (x >= DOT_X)
    trapezoid = HIGH_Y + (GOAL_X - x) * (DOT_Y - HIGH_Y) / (GOAL_X - DOT_X)
    level = np.select(
        [deep & (ya <= HIGH_Y),
         deep & (ya <= trapezoid),
         in_front & (x >= CIRCLE_TOP_X) & (x < DOT_X) & (ya <= DOT_Y)],
        [2, 1, 1], default=0)
    level = np.minimum(level + np.asarray(rush, dtype=int), 2)
    level = np.where(np.asarray(royal_road, dtype=bool), 2, level)
    level = np.maximum(level - np.asarray(blocked, dtype=int), 0)
    return np.array(TIERS)[level]
