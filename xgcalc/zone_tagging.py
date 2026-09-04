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
