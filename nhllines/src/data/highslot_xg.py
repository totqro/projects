"""
High Slot per-game team xG, as an alternative to MoneyPuck's.
==============================================================
High Slot (../fortknox, https://highslot.web.app) scores every NHL shot with
its own full-data xG model, trained on the NHL's feed. This module returns
its xG in the same {nhl_game_id: {team_abbrev: {...}}} shape as
moneypuck_data.load_moneypuck_xg(), so build_point_in_time_rows() and
build_live_state() take it unchanged.

The data is data/highslot_team_game_xg.json, written by
fortknox/pipeline/export_team_game_xg.py. Completed seasons there are scored
walk-forward (season S by a model that never saw S), so the xG features
carry no in-sample goal information.

Two variants:
- "ev5": xgf_adj/xga_adj are 5v5 xG at any score, with no high-danger split
  (hd_xgf/hd_xga are 0; drop that column). This is what High Slot's public
  games.json publishes per game (hxg5/axg5), so it is the variant a served
  model could read live.
- "close": xgf_adj/xga_adj are 5v5 xG with the score within one, plus the
  high-danger split: MoneyPuck's definition, for a like-for-like comparison.

Used by highslot_gate.py only. Its verdict (README item 12): High Slot's xG
matches MoneyPuck's in the win model, so nothing serves from it.
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
HIGHSLOT_XG_PATH = DATA_DIR / "highslot_team_game_xg.json"

VARIANTS = ("ev5", "close")


def _shape(team: dict, variant: str) -> dict:
    """One team's totals in moneypuck_data's per-team shape for `variant`."""
    if variant == "ev5":
        return {"is_home": team["is_home"], "xgf": team["xgf"], "xga": team["xga"],
                "xgf_adj": team["xgf5"], "xga_adj": team["xga5"],
                "hd_xgf": 0.0, "hd_xga": 0.0}
    if variant == "close":
        return {k: team[k] for k in
                ("is_home", "xgf", "xga", "xgf_adj", "xga_adj", "hd_xgf", "hd_xga")}
    raise ValueError(f"Unknown High Slot xG variant {variant!r}, expected one of {VARIANTS}")


def load_highslot_xg(seasons: list, variant: str = "ev5",
                     path: Path = HIGHSLOT_XG_PATH) -> dict:
    """Training xG for `seasons` ('20222023' style) from the exported file.
    Raises if the file is missing or doesn't cover a requested season:
    training on placeholder xG would gate a model on nothing."""
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is missing. Write it with "
            f"fortknox/pipeline/export_team_game_xg.py.")
    data = json.loads(path.read_text())
    years = {int(s[:4]) for s in seasons}
    missing = sorted(y for y in years if str(y) not in data["provenance"])
    if missing:
        raise ValueError(f"{path} has no High Slot xG for season(s) starting {missing}")
    out = {}
    for gid, teams in data["games"].items():
        gid = int(gid)
        if gid // 1_000_000 in years:
            out[gid] = {t: _shape(v, variant) for t, v in teams.items()}
    return out

