"""
Frozen model constants. Every number here was chosen by leave-one-season-out
cross-validation inside 2015-2023 (the experiment that chose it is named);
nothing was tuned on 2024-2025.
"""

# Stage 0 — Elo (experiments/stage0_elo_tune.py, nested LOSO over K/HFA/reversion)
ELO_HFA = 35.0             # Elo points of home field (~1.3 pts of margin)
ELO_REVERSION = 1.0 / 3.0  # flat season-boundary regression toward 1500 (Stage 2 could not beat it over a full season)
ELO_K_STAGE0 = 20.0        # K for the plain Elo baseline

# Stage 1 — QB-adjusted Elo (experiments/stage1_qb_elo.py, stage1b_qb_elo_ext.py)
ELO_K = 15.0               # K once the QB is carried separately
QB_ELO_SCALE = 800.0       # Elo points per 1.0 EPA/dropback of shrunk QB rating
QB_N0 = 200.0              # pseudo-dropbacks of prior
QB_DECAY = 0.8             # per-season weight on earlier seasons' dropbacks

# Stage 2 — week-1 prior: lives in the win model as early-decayed features
# (experiments/stage2_*.py); EARLY_GAMES is in src/features/engine.py.

# Stage 3 — efficiency tracker (experiments/stage3b_ewma.py)
EFF_LAMBDA = 0.9           # per-game weight decay
EFF_SEASON_DISCOUNT = 0.8  # extra discount per season boundary
EFF_N0 = 6.0               # games of league-average prior

# Stage 4 — injuries (experiments/stage4_injuries.py)
INJ_DRAFT_WEIGHT = 0.03    # cap-% equivalent of a #1 overall pick's draft value
INJ_WINDOW = 8             # games over which "missed share" is measured

# Elo points per point of margin, measured on the training games
ELO_PER_POINT = 27.7
