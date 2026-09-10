"""
Schema for the xG shot dataset.
===============================

One place that defines (a) which raw MoneyPuck shot columns we read, (b) what
each becomes after cleaning, and (c) which cleaned columns are legitimate
model features versus identifiers, labels, or benchmarks.

The raw MoneyPuck shots file has 124-137 columns depending on season (2020 and
2024 carry extra win-probability/score columns the other seasons lack). Every
column named in SOURCE_COLUMNS was verified present in all of 2018-2025, so
the reader can use a fixed usecols list across seasons.
"""

# --- Raw columns read from the MoneyPuck shots CSV -------------------------
# Verified present in every season 2018-2025. Anything not listed here is
# never read, which keeps a ~65MB/season CSV down to a manageable frame.
SOURCE_COLUMNS = [
    # identifiers / game context
    "shotID", "game_id", "season", "isPlayoffGame", "period", "time",
    "timeSinceFaceoff",
    # coordinates
    "xCord", "yCord", "xCordAdjusted", "yCordAdjusted",
    "arenaAdjustedXCordABS", "arenaAdjustedYCordAbs",
    # geometry as MoneyPuck computes it
    "shotDistance", "arenaAdjustedShotDistance", "shotAngle", "shotAngleAdjusted",
    # the shot itself
    "shotType", "event", "goal", "shotWasOnGoal",
    # play context / sequence
    "shotRebound", "shotRush", "lastEventCategory",
    "lastEventxCord_adjusted", "lastEventyCord_adjusted",
    "timeSinceLastEvent", "distanceFromLastEvent", "speedFromLastEvent",
    # strength state / empty net
    "homeSkatersOnIce", "awaySkatersOnIce", "isHomeTeam",
    "homeEmptyNet", "awayEmptyNet", "shotOnEmptyNet",
    # shooter
    "shooterPlayerId", "shooterName", "shooterLeftRight", "offWing",
    "playerPositionThatDidEvent", "shooterTimeOnIce",
    # goalie
    "goalieIdForShot", "goalieNameForShot",
    # teams and score
    "teamCode", "homeTeamCode", "awayTeamCode", "homeTeamGoals", "awayTeamGoals",
    # MoneyPuck's own xG — benchmark only, NEVER a feature
    "xGoal",
]

# --- Rink geometry ---------------------------------------------------------
# NHL rink, coordinates in feet. In the "adjusted" frame every shot attacks
# the net at x = +89, so x runs 0 (centre ice) to ~100 (end boards) and y runs
# -42.5 (one side) to +42.5 (the other).
GOAL_LINE_X = 89.0
BLUE_LINE_X = 25.0        # offensive blue line in the adjusted frame
GOAL_MOUTH_HALF_WIDTH = 3.0   # net is 6 ft wide

# --- Model features --------------------------------------------------------
# These are the columns a model may train on. Split by kind so the training
# code can one-hot the categoricals without hardcoding names again.
NUMERIC_FEATURES = [
    "x_adj", "y_adj", "y_abs",
    "distance", "distance_arena_adj",
    "angle_abs", "angle_from_net",
    "time_since_last_event", "distance_from_last_event", "speed_from_last_event",
    "prev_event_x", "prev_event_y",
    "shooting_skaters", "defending_skaters", "skater_differential",
    "score_differential", "period", "time_seconds", "time_since_faceoff",
    "shooter_toi",
]

BINARY_FEATURES = [
    "is_rebound", "is_behind_net", "is_empty_net", "shooter_net_empty",
    "pulled_goalie_state", "is_overtime",
    "off_wing", "is_home", "is_playoff", "shot_type_missing", "speed_imputed",
]

CATEGORICAL_FEATURES = [
    "shot_type", "strength_state", "strength_bucket", "period_format", "situation",
    "prev_event", "prev_event_zone", "shooter_hand", "shooter_position",
]

FEATURE_COLUMNS = NUMERIC_FEATURES + BINARY_FEATURES + CATEGORICAL_FEATURES

# --- Non-features ----------------------------------------------------------
LABEL_COLUMN = "goal"

IDENTIFIER_COLUMNS = [
    "shot_id", "game_id", "season", "event",
    "shooter_id", "shooter_name", "goalie_id", "goalie_name",
    "team", "home_team", "away_team",
]

# Columns that must never be fed to a model: they either ARE the answer or
# encode it. `mp_xg` is MoneyPuck's own model output, kept only so we can
# benchmark ours against it. `was_on_goal` is known only after the shot
# resolves, and `is_rush_mp` is retained purely for documentation of a known
# bad field (see clean.py and the README).
LEAKY_COLUMNS = ["mp_xg", "was_on_goal", "goal"]

# MoneyPuck's raw shot-angle convention, kept for reference/comparison but not
# used as a feature — it mirrors behind-the-net shots back into +/-90 degrees.
REFERENCE_COLUMNS = ["mp_shot_angle", "is_rush_mp"]


# --- Evaluation protocol ---------------------------------------------------
# Seasons that must NEVER enter a training set. Held permanently out so there
# is always a season the model has not seen, which is the only way to measure
# whether it generalises to a season rather than to this dataset.
#
# 2024 is the selection/validation season: tune, compare encodings, and choose
# features against it. 2025 is the final test season.
#
# Honest accounting of what has already been looked at: the five-feature
# choice and the strength-encoding choice were originally made against 2025,
# then re-checked on 2024. Both have therefore informed decisions, so neither
# is a virgin holdout any more. Treat published numbers on them as
# optimistic by a small margin, and seal a genuinely fresh season (2026+)
# before making any claim that has to survive outside scrutiny.
HOLDOUT_SEASONS = frozenset({2024, 2025})
VALIDATION_SEASON = 2024
TEST_SEASON = 2025


def assert_no_holdout_leak(train_df) -> None:
    """Raise if a training frame contains a held-out season.

    Called by every script that fits a model. A guard rather than a comment
    because "remember not to train on 2024" is exactly the kind of rule that
    quietly breaks six months later.
    """
    leaked = sorted(set(train_df["season"].unique()) & HOLDOUT_SEASONS)
    if leaked:
        raise ValueError(
            f"Training data contains held-out season(s) {leaked}. "
            f"{sorted(HOLDOUT_SEASONS)} are reserved for evaluation and must "
            f"never be trained on — see HOLDOUT_SEASONS in schema.py."
        )
