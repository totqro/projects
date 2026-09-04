"""
Clean MoneyPuck shot rows into an xG-ready table.
=================================================

Every transform here is deliberate, and the ones that correct or reject
MoneyPuck's own fields are documented inline with what was measured. Nothing
is silently dropped: rows removed are counted and reported by build_dataset.

Known issues in the raw data, and what we do about them
------------------------------------------------------
1. `shotAngle` mirrors behind-the-net shots. MoneyPuck computes the angle
   against |89 - x|, so a shot from x=96,y=11 (six feet BEHIND the goal line)
   is reported as 57.5 degrees, identical to a shot from x=82,y=11 in front of
   the net. Roughly 1.6% of shots are behind the goal line. We keep their
   column as `mp_shot_angle` for reference and compute `angle_from_net`
   (0-180 degrees, where >90 means behind the goal line) plus an
   `is_behind_net` flag.

2. `shotRush` is not usable. Its rate decays from 0.25% (2018) to 0.06%
   (2025) — real rush-shot rates are one to two orders of magnitude higher, so
   the flag is either broken or means something much narrower than "rush". It
   is carried through as `is_rush_mp` for documentation only and is excluded
   from FEATURE_COLUMNS. Rush detection should be engineered from the
   prev-event columns at modelling time (see README).

3. `speedFromLastEvent` divides by zero-second gaps. When
   timeSinceLastEvent == 0, MoneyPuck reports speed equal to the raw distance
   (an implicit divide-by-1), which is not a speed. ~1% of shots. We reproduce
   the same value so the column stays comparable, but flag it with
   `speed_imputed` so a model can learn to distrust it.

4. `shotType` is missing on ~0.1-1% of shots (rising in recent seasons).
   Filled with "UNKNOWN" and flagged with `shot_type_missing` rather than
   dropped — a missing shot type is itself weakly informative and dropping
   would bias against recent seasons.

5. `shooterLeftRight` is missing on ~3% of shots. Filled with "U".

6. Period number does not identify the game situation. Regular-season
   period 4 is 3-on-3 overtime; playoff period 4+ is 5-on-5. Regular-season
   period 5 would be the shootout. See period_format below, and the shootout
   drop above.

7. Team codes change style mid-archive. 2018-2020 use "L.A"/"N.J"/"S.J"/
   "T.B", 2021+ use "LAK"/"NJD"/"SJS"/"TBL" — the same four franchises under
   two labels across 38,361 shots. Normalised to the NHL-API form, with an
   unrecognised code raising rather than passing through.

8. Skaters-on-ice does not equal strength state. `homeSkatersOnIce` /
   `awaySkatersOnIce` count skaters, so a pulled goalie reads as an extra
   man. Bucketing on the raw difference labels 5v6 (empty net) as
   shorthanded and 6v5 (own net pulled) as a power play. We keep the raw
   count as `strength_state` and compute `strength_bucket` from
   goalie-adjusted counts instead. See the strength-state section below.
"""

import numpy as np
import pandas as pd

from .schema import BLUE_LINE_X, GOAL_LINE_X

# Values seen 2018-2025. Anything outside these is a parsing problem, not a
# hockey event, and gets dropped with a count rather than clipped silently.
# A goalie pull for an extra attacker is a last-10-minutes-of-regulation
# tactic. Used with a trailing-score requirement to tell a pull apart from a
# delayed penalty; see the situation block in clean_shots().
PULL_TIME_SECONDS = 3000

VALID_SKATERS = {3, 4, 5, 6, 7}
MAX_ABS_X, MAX_ABS_Y = 100.0, 45.0

# MoneyPuck changed team-code style mid-archive: seasons 2018-2020 use the
# dotted "L.A"/"N.J"/"S.J"/"T.B" form and 2021+ use NHL-API codes. Left
# alone, Los Angeles' 2018-2020 shots sit under a different team label than
# its 2021+ shots (38,361 shots across the four clubs), silently splitting
# every team-level split in half. Normalised to the NHL-API form.
# ARI and UTA stay distinct on purpose — those are different franchises.
TEAM_CODE_FIXES = {"L.A": "LAK", "N.J": "NJD", "S.J": "SJS", "T.B": "TBL",
                   "PHX": "ARI"}

# Every code seen in 2018-2025 after normalisation. An unrecognised code is
# raised rather than passed through, so a future relocation or a new archive
# style is caught at build time instead of becoming a silent extra "team".
KNOWN_TEAMS = {
    "ANA", "ARI", "BOS", "BUF", "CAR", "CBJ", "CGY", "CHI", "COL", "DAL",
    "DET", "EDM", "FLA", "LAK", "MIN", "MTL", "NJD", "NSH", "NYI", "NYR",
    "OTT", "PHI", "PIT", "SEA", "SJS", "STL", "TBL", "TOR", "UTA", "VAN",
    "VGK", "WPG", "WSH",
}


def _normalize_team(codes: pd.Series) -> pd.Series:
    """Map MoneyPuck team codes onto one consistent style, loudly."""
    fixed = codes.replace(TEAM_CODE_FIXES)
    unknown = set(fixed.dropna().unique()) - KNOWN_TEAMS
    if unknown:
        raise ValueError(
            f"Unrecognised team code(s) {sorted(unknown)} — add them to "
            f"TEAM_CODE_FIXES/KNOWN_TEAMS in clean.py. Refusing to build a "
            f"dataset where one franchise appears under two labels."
        )
    return fixed.astype("string")


def _zone(x_adj: pd.Series) -> pd.Series:
    """Zone of a point in the attacking-right frame: offensive (past the
    offensive blue line), neutral, or defensive."""
    return pd.Series(
        np.select(
            [x_adj > BLUE_LINE_X, x_adj >= -BLUE_LINE_X],
            ["OFF", "NEU"],
            default="DEF",
        ),
        index=x_adj.index,
        dtype="object",
    )


def clean_shots(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Turn one season's raw MoneyPuck shot rows into the cleaned schema.

    Returns (cleaned_frame, drop_report). The report counts every row removed
    and why, so the builder can print an honest accounting.
    """
    df = raw.copy()
    n_start = len(df)
    report: dict[str, int] = {"rows_in": n_start}

    # --- Row-level validity -------------------------------------------------
    # Only real shot attempts. MoneyPuck's file already excludes blocked
    # shots; this guards against anything unexpected in older archives.
    valid_event = df["event"].isin(["SHOT", "MISS", "GOAL"])
    report["dropped_bad_event"] = int((~valid_event).sum())
    df = df[valid_event]

    coords_ok = (
        df[["xCord", "yCord", "xCordAdjusted", "yCordAdjusted"]].notna().all(axis=1)
        & df["xCordAdjusted"].abs().le(MAX_ABS_X)
        & df["yCordAdjusted"].abs().le(MAX_ABS_Y)
    )
    report["dropped_bad_coords"] = int((~coords_ok).sum())
    df = df[coords_ok]

    skaters_ok = df["homeSkatersOnIce"].isin(VALID_SKATERS) & df[
        "awaySkatersOnIce"
    ].isin(VALID_SKATERS)
    report["dropped_bad_strength"] = int((~skaters_ok).sum())
    df = df[skaters_ok]

    goal_ok = df["goal"].isin([0, 1])
    report["dropped_bad_label"] = int((~goal_ok).sum())
    df = df[goal_ok]

    # Shootout attempts are not shots. A regular-season game has three
    # regulation periods plus one OT period, so anything at period >= 5 in a
    # non-playoff game is the shootout: a penalty shot from a standing start,
    # converted around a third of the time, with no defenders and no rebound.
    # Training on them would poison the model. MoneyPuck appears to exclude
    # them already (zero such rows across 2018-2025), but this drops and
    # COUNTS them so a future archive that includes them cannot slip through.
    shootout = (df["isPlayoffGame"].fillna(0) == 0) & (df["period"] >= 5)
    report["dropped_shootout"] = int(shootout.sum())
    df = df[~shootout].reset_index(drop=True)

    out = pd.DataFrame(index=df.index)

    # --- Identifiers --------------------------------------------------------
    out["shot_id"] = df["shotID"].astype("int64")
    out["game_id"] = df["game_id"].astype("int64")
    out["season"] = df["season"].astype("int16")
    out["is_playoff"] = df["isPlayoffGame"].fillna(0).astype("int8")
    out["event"] = df["event"].astype("string")

    # --- Time ---------------------------------------------------------------
    out["period"] = df["period"].astype("int8")
    out["time_seconds"] = df["time"].astype("int32")           # elapsed game seconds
    out["time_since_faceoff"] = df["timeSinceFaceoff"].astype("int32")

    # Overtime format. The period number alone is ambiguous and actively
    # misleading: regular-season OT is five minutes of 3-on-3 on wide-open
    # ice, while playoff OT is full 20-minute 5-on-5. Both are "period 4".
    # Measured at even strength, they are opposite environments — 3v3 OT
    # scores at .1305 from a median 24 ft, playoff OT at .0530 from 35 ft,
    # against .0644 in regulation. A model given a raw period number has to
    # untangle a 2.5x difference in danger from an interaction with
    # is_playoff; naming the format directly hands it that for free.
    out["is_overtime"] = (df["period"] >= 4).astype("int8")
    out["period_format"] = pd.Series(
        np.select(
            [df["period"] <= 3, out["is_playoff"] == 1],
            ["REGULATION", "OT_5v5"],
            default="OT_3v3",
        ),
        index=df.index,
        dtype="object",
    ).astype("string")

    # --- Coordinates --------------------------------------------------------
    # x_adj/y_adj are flipped so every shot attacks the net at x = +89,
    # which is what makes shots from both ends comparable. Verified: in the
    # adjusted frame x is always >= 0 and y stays within +/-42.
    out["x_raw"] = df["xCord"].astype("float32")
    out["y_raw"] = df["yCord"].astype("float32")
    out["x_adj"] = df["xCordAdjusted"].astype("float32")
    out["y_adj"] = df["yCordAdjusted"].astype("float32")
    out["y_abs"] = df["yCordAdjusted"].abs().astype("float32")
    # Arena-bias-corrected coordinates: MoneyPuck rescales for the fact that
    # each arena's scorer records distance with a consistent bias.
    out["x_arena_adj"] = df["arenaAdjustedXCordABS"].astype("float32")
    out["y_arena_adj"] = df["arenaAdjustedYCordAbs"].astype("float32")

    # --- Geometry -----------------------------------------------------------
    # shotDistance is exactly sqrt((89-x)^2 + y^2) in the adjusted frame
    # (verified to 5e-11), so we take it as-is rather than recomputing.
    out["distance"] = df["shotDistance"].astype("float32")
    out["distance_arena_adj"] = df["arenaAdjustedShotDistance"].astype("float32")

    out["mp_shot_angle"] = df["shotAngle"].astype("float32")     # see issue 1
    out["angle_abs"] = df["shotAngle"].abs().astype("float32")

    # Our own angle: 0 = straight on, 90 = level with the goal line,
    # >90 = behind the net. Unlike MoneyPuck's, this does not fold
    # behind-the-net shots onto in-front ones.
    dx = GOAL_LINE_X - out["x_adj"]
    out["angle_from_net"] = np.degrees(
        np.arctan2(out["y_abs"], dx)
    ).astype("float32")
    out["is_behind_net"] = (out["x_adj"] > GOAL_LINE_X).astype("int8")

    # --- The shot -----------------------------------------------------------
    out["shot_type_missing"] = df["shotType"].isna().astype("int8")
    out["shot_type"] = df["shotType"].fillna("UNKNOWN").astype("string")

    # --- Play context / sequence -------------------------------------------
    out["is_rebound"] = df["shotRebound"].fillna(0).astype("int8")
    out["is_rush_mp"] = df["shotRush"].fillna(0).astype("int8")   # see issue 2

    out["prev_event"] = df["lastEventCategory"].fillna("NONE").astype("string")
    out["prev_event_x"] = df["lastEventxCord_adjusted"].astype("float32")
    out["prev_event_y"] = df["lastEventyCord_adjusted"].astype("float32")
    out["prev_event_zone"] = _zone(df["lastEventxCord_adjusted"]).astype("string")

    time_since = df["timeSinceLastEvent"].fillna(0).clip(lower=0)
    out["time_since_last_event"] = time_since.astype("float32")
    out["distance_from_last_event"] = (
        df["distanceFromLastEvent"].astype("float32")
    )
    # Reproduce MoneyPuck's speed (distance / max(seconds, 1)) so the column
    # stays comparable to theirs, and flag the zero-gap rows. See issue 3.
    out["speed_imputed"] = (time_since <= 0).astype("int8")
    out["speed_from_last_event"] = (
        df["distanceFromLastEvent"] / time_since.clip(lower=1)
    ).astype("float32")

    # --- Strength state -----------------------------------------------------
    is_home = df["isHomeTeam"].astype(float).eq(1)
    out["is_home"] = is_home.astype("int8")

    shooting = np.where(is_home, df["homeSkatersOnIce"], df["awaySkatersOnIce"])
    defending = np.where(is_home, df["awaySkatersOnIce"], df["homeSkatersOnIce"])
    out["shooting_skaters"] = pd.Series(shooting, index=df.index).astype("int8")
    out["defending_skaters"] = pd.Series(defending, index=df.index).astype("int8")
    out["skater_differential"] = (
        out["shooting_skaters"] - out["defending_skaters"]
    ).astype("int8")

    # Raw skaters-on-ice state, e.g. "5v5", "5v4", "5v6". Descriptive only —
    # see strength_bucket below for why this is NOT the man-advantage state.
    out["strength_state"] = (
        out["shooting_skaters"].astype(str) + "v" + out["defending_skaters"].astype(str)
    ).astype("string")

    # Empty net, from the shooter's point of view. The net being SHOT AT is
    # the opponent's: verified to agree with MoneyPuck's shotOnEmptyNet on
    # 100% of 2024 rows, so the derivation is sound in both directions.
    out["is_empty_net"] = (
        np.where(is_home, df["awayEmptyNet"], df["homeEmptyNet"])
    ).astype("int8")
    out["shooter_net_empty"] = (
        np.where(is_home, df["homeEmptyNet"], df["awayEmptyNet"])
    ).astype("int8")
    out["pulled_goalie_state"] = (
        (out["is_empty_net"] | out["shooter_net_empty"])
    ).astype("int8")

    # Man-advantage state, adjusted for pulled goalies. Raw skater counts
    # alone get this wrong: a team that pulls its goalie puts a sixth skater
    # on the ice without earning a man advantage, so "5v6" is even strength
    # against an empty net, not a penalty kill, and "6v5" is even strength
    # with your own net empty, not a power play. Measured on 2024: naive
    # skater-count bucketing put 878 5v6 and 59 4v6 shots in "SH", dragging
    # its apparent goal rate to .201 (vs .073 for true penalty-kill shots),
    # and 2,961 pulled-goalie shots into "PP". Subtracting the pulled goalie
    # from each side's count before comparing fixes both.
    eff_shooting = out["shooting_skaters"] - out["shooter_net_empty"]
    eff_defending = out["defending_skaters"] - out["is_empty_net"]
    out["strength_bucket"] = pd.Series(
        np.select(
            [eff_shooting > eff_defending, eff_shooting < eff_defending],
            ["PP", "SH"],
            default="EV",
        ),
        index=df.index,
        dtype="object",
    ).astype("string")

    # --- Shooter ------------------------------------------------------------
    out["shooter_id"] = df["shooterPlayerId"].astype("Int64")
    out["shooter_name"] = df["shooterName"].astype("string")
    out["shooter_hand"] = df["shooterLeftRight"].fillna("U").astype("string")
    out["off_wing"] = df["offWing"].fillna(0).astype("int8")
    out["shooter_position"] = (
        df["playerPositionThatDidEvent"].fillna("U").astype("string")
    )
    out["shooter_toi"] = df["shooterTimeOnIce"].fillna(0).astype("float32")

    # --- Goalie -------------------------------------------------------------
    out["goalie_id"] = df["goalieIdForShot"].astype("Int64")
    out["goalie_name"] = df["goalieNameForShot"].astype("string")

    # --- Teams and score ----------------------------------------------------
    out["team"] = _normalize_team(df["teamCode"])
    out["home_team"] = _normalize_team(df["homeTeamCode"])
    out["away_team"] = _normalize_team(df["awayTeamCode"])
    home_goals = df["homeTeamGoals"].fillna(0)
    away_goals = df["awayTeamGoals"].fillna(0)
    # Score differential from the SHOOTING team's perspective, at shot time.
    out["score_differential"] = np.where(
        is_home, home_goals - away_goals, away_goals - home_goals
    ).astype("int8")

    # --- Situation ----------------------------------------------------------
    # A single categorical naming what is actually happening on the ice, for
    # use as the strength term in the model. Skater counts alone cannot say
    # this: 6v5 has two entirely different causes.
    #
    #   Delayed penalty - the offending team cannot touch the puck, so play
    #   stops the moment they do. The goalie comes off with zero risk of a
    #   goal against, and the shooting team gets a settled possession. Happens
    #   at any point in a game and at any score.
    #
    #   Pulled goalie - a trailing team trades its net for an extra attacker
    #   late. Real empty-net risk, desperation, broken play.
    #
    # They are separated by three signals, in order: a DELPEN previous event
    # is definitive; a pull requires the team to be TRAILING (you cannot pull
    # while ahead - a hard constraint, and the split below produces 0
    # violations); and a pull happens late. Measured on 2018-2025: the pulled
    # group is 100% trailing with a 5th-percentile time of 3,361s (56 min),
    # while the delayed-penalty group is 37% trailing with a median of
    # 1,706s (28 min). Only 39 of 19,746 rows are genuinely ambiguous.
    own_net_empty = out["shooter_net_empty"] == 1
    pulled = (
        own_net_empty
        & (out["prev_event"] != "DELPEN")
        & (out["score_differential"] < 0)
        & (out["time_seconds"] >= PULL_TIME_SECONDS)
    )
    state = out["strength_state"]

    out["situation"] = pd.Series(
        np.select(
            [
                # Shooting AT an empty net dominates everything else.
                out["is_empty_net"] == 1,
                # Own net empty, shooting at a goalie.
                own_net_empty & (state == "6v5") & pulled,
                own_net_empty & (state == "6v5") & ~pulled,
                own_net_empty & pulled,
                own_net_empty,
                # Both nets guarded.
                state == "5v5",
                state == "5v4",
                state == "4v5",
                state == "4v4",
                state == "3v3",
                state == "5v3",
                state == "4v3",
                out["strength_bucket"] == "PP",
                out["strength_bucket"] == "SH",
            ],
            [
                "EN_AGAINST",
                "EN_6v5_PULLED",
                "EN_6v5_DELAYED_PEN",
                "EN_OTHER_PULLED",
                "EN_OTHER_DELAYED_PEN",
                "EV_5v5",
                "PP_5v4",
                "SH_4v5",
                "EV_4v4",
                "EV_3v3",
                "PP_5v3",
                "PP_4v3",
                "PP_OTHER",
                "SH_OTHER",
            ],
            default="OTHER",
        ),
        index=df.index,
        dtype="object",
    ).astype("string")

    # --- Label and benchmark ------------------------------------------------
    out["goal"] = df["goal"].astype("int8")
    out["was_on_goal"] = df["shotWasOnGoal"].fillna(0).astype("int8")
    out["mp_xg"] = df["xGoal"].astype("float32")   # benchmark only, not a feature

    report["rows_out"] = len(out)
    report["dropped_total"] = n_start - len(out)
    return out.reset_index(drop=True), report
