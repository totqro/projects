"""
Tagged-only features: what a rinkside tagger can see that MoneyPuck can't.

    odd-man rush       tagged live (f in the tracker)
    cross-ice pass     a royal-road pass: passer and shooter on opposite
                       sides of the royal road (beyond the posts' lines,
                       |y| > 3 ft), both below the tops of the faceoff
                       circles (x >= 54 ft), shot within 0.5 s (p in the
                       tracker). The tracker only knows the shooter, so a
                       tag on a shooter outside that area doesn't count.
    blocked shot       priced at a fraction of its unblocked xG, not zero

None of these can be fit on the 905,483 NHL shots: MoneyPuck carries no
passes, its rush flag is broken (README, "shotRush is unusable"), and its
file excludes blocks. So they sit on top of the five-feature model as a
separate layer:

    z  = logit(base xG) + rush * b_rush + cross_ice * b_cross
    xG = sigmoid(z), times block_factor if the attempt was blocked

b_cross's prior is measured on real games (bdc_royal_road.py, Big Data Cup
pass data); b_rush's is a judgment call, since no public data counts who is
back. Both are refit on tagged games by fit_tagged.py, shrunk toward the
prior. block_factor is measured by fit_tagged.py from goals tagged as going
in off a defender, against the blocks: 0.25 until there are enough.

The numbers live in tag_adjustments.json. export_model_web.py copies them
into xg_model.json so the tracker and shot chart score the same way.
"""

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
ADJUSTMENTS_PATH = ROOT / "tag_adjustments.json"

POST_Y = 3.0              # posts sit 3 ft either side of the net's centre
CIRCLE_TOP_X = 54.0       # faceoff dots at x = 69, circles 15 ft in radius
CROSS_ICE_WINDOW_S = 0.5  # pass to shot


def load_adjustments(path: Path = ADJUSTMENTS_PATH) -> dict:
    return json.loads(path.read_text())


def logit(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-12, 1 - 1e-12)
    return np.log(p / (1 - p))


def royal_road_spot(x, y):
    """Can a royal-road pass end here? Below the circle tops, off the road.
    Attacking frame (net at x = 89). Holds for the passer's spot too."""
    x = np.asarray(x, dtype=float); y = np.asarray(y, dtype=float)
    return (x >= CIRCLE_TOP_X) & (np.abs(y) > POST_Y)


def adjust(base_xg, rush, cross_ice, blocked, adj: dict | None = None):
    """Apply the tagged layer to base-model xG. All inputs are arrays;
    cross_ice should already be gated by royal_road_spot."""
    adj = adj or load_adjustments()
    z = (logit(base_xg)
         + np.asarray(rush, dtype=float) * adj["rush"]["coef"]
         + np.asarray(cross_ice, dtype=float) * adj["cross_ice"]["coef"])
    xg = 1.0 / (1.0 + np.exp(-z))
    return np.where(np.asarray(blocked, dtype=bool), xg * adj["block_factor"], xg)


def crosses_royal_road(pass_x, pass_y, shot_x, shot_y) -> bool:
    """True for a pass from (pass_x, pass_y) to a shot at (shot_x, shot_y)
    that is a royal-road pass: both spots below the circle tops and off the
    road, on opposite sides of it. Attacking frame."""
    return bool(royal_road_spot(pass_x, pass_y) and royal_road_spot(shot_x, shot_y)
                and np.sign(pass_y) != np.sign(shot_y))
