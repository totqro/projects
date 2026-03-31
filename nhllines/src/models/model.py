"""
NHL Betting Model
Compares current matchups to similar historical games to estimate
true win probabilities, expected total goals, and spread coverage.
Uses these to find +EV bets.
"""

import math
from typing import Optional
from functools import lru_cache


def calculate_similarity(
    home_stats: dict,
    away_stats: dict,
    hist_home_stats: dict,
    hist_away_stats: dict,
    h2h: dict,
    hist_game: dict,
    current_home: str,
    current_away: str,
) -> float:
    """
    Calculate how similar a historical game is to the current matchup.
    Returns a similarity score (higher = more similar, max ~1.0).

    Factors:
    - Team quality differential (points %, win %)
    - Offensive/defensive strength match
    - Home/away context
    - Head-to-head relevance
    """
    score = 0.0
    max_score = 0.0

    # 1. Team quality differential similarity (weight: 3)
    # Compare the gap between teams in current vs historical
    weight = 3.0
    max_score += weight
    current_diff = home_stats.get("win_pct", 0.5) - away_stats.get("win_pct", 0.5)
    hist_diff = hist_home_stats.get("win_pct", 0.5) - hist_away_stats.get("win_pct", 0.5)
    quality_sim = 1.0 - min(abs(current_diff - hist_diff), 1.0)
    score += weight * quality_sim

    # 2. Home team offensive strength similarity (weight: 2)
    weight = 2.0
    max_score += weight
    current_home_gf = home_stats.get("avg_gf", 3.0)
    hist_home_gf = hist_home_stats.get("avg_gf", 3.0)
    off_sim = 1.0 - min(abs(current_home_gf - hist_home_gf) / 3.0, 1.0)
    score += weight * off_sim

    # 3. Away team offensive strength similarity (weight: 2)
    weight = 2.0
    max_score += weight
    current_away_gf = away_stats.get("avg_gf", 3.0)
    hist_away_gf = hist_away_stats.get("avg_gf", 3.0)
    off_sim2 = 1.0 - min(abs(current_away_gf - hist_away_gf) / 3.0, 1.0)
    score += weight * off_sim2

    # 4. Home team defensive strength similarity (weight: 2)
    weight = 2.0
    max_score += weight
    current_home_ga = home_stats.get("avg_ga", 3.0)
    hist_home_ga = hist_home_stats.get("avg_ga", 3.0)
    def_sim = 1.0 - min(abs(current_home_ga - hist_home_ga) / 3.0, 1.0)
    score += weight * def_sim

    # 5. Away team defensive strength similarity (weight: 2)
    weight = 2.0
    max_score += weight
    current_away_ga = away_stats.get("avg_ga", 3.0)
    hist_away_ga = hist_away_stats.get("avg_ga", 3.0)
    def_sim2 = 1.0 - min(abs(current_away_ga - hist_away_ga) / 3.0, 1.0)
    score += weight * def_sim2

    # 6. Same teams bonus (weight: 2)
    weight = 2.0
    max_score += weight
    if (hist_game["home_team"] == current_home and hist_game["away_team"] == current_away):
        score += weight  # Exact same matchup
    elif (hist_game["home_team"] == current_away and hist_game["away_team"] == current_home):
        score += weight * 0.5  # Same teams, reversed home/away
    # else: no bonus

    # 7. Points percentage similarity for both teams (weight: 2)
    weight = 2.0
    max_score += weight
    current_home_ppct = home_stats.get("points_pct", 0.5)
    hist_home_ppct = hist_home_stats.get("points_pct", 0.5)
    current_away_ppct = away_stats.get("points_pct", 0.5)
    hist_away_ppct = hist_away_stats.get("points_pct", 0.5)
    ppct_sim = 1.0 - (
        abs(current_home_ppct - hist_home_ppct) +
        abs(current_away_ppct - hist_away_ppct)
    ) / 2.0
    score += weight * max(ppct_sim, 0)

    return score / max_score if max_score > 0 else 0.0


def _build_form_index(all_games: list, n: int = 10) -> dict:
    """
    Pre-compute point-in-time form for every team at every game date in O(n) time.
    Returns dict: {(team, date): {win_pct, avg_gf, avg_ga, points_pct}}

    Instead of scanning all games per lookup (O(n*m)), this sorts games once
    and maintains a rolling window per team.
    """
    from collections import deque

    # Sort completed games by date
    completed = [
        g for g in all_games
        if g.get("game_state") in ("OFF", "FINAL") and g.get("date")
    ]
    completed.sort(key=lambda g: g["date"])

    # Track each team's recent game results as a rolling deque
    team_history = {}  # team -> deque of (win, gf, ga)
    form_index = {}    # (team, date) -> form_dict
    default_form = {"win_pct": 0.5, "avg_gf": 3.0, "avg_ga": 3.0, "points_pct": 0.5}

    # Track which teams appear on each date so we can snapshot form BEFORE the game
    games_by_date = {}
    for g in completed:
        d = g["date"]
        if d not in games_by_date:
            games_by_date[d] = []
        games_by_date[d].append(g)

    for date in sorted(games_by_date.keys()):
        date_games = games_by_date[date]

        # Snapshot form for all teams playing TODAY (before today's games are added)
        for g in date_games:
            for team in (g["home_team"], g["away_team"]):
                if (team, date) not in form_index:
                    history = team_history.get(team)
                    if history and len(history) > 0:
                        wins = sum(r[0] for r in history)
                        gf = sum(r[1] for r in history)
                        ga = sum(r[2] for r in history)
                        ng = len(history)
                        form_index[(team, date)] = {
                            "win_pct": wins / ng,
                            "avg_gf": gf / ng,
                            "avg_ga": ga / ng,
                            "points_pct": wins / ng,
                        }
                    else:
                        form_index[(team, date)] = default_form

        # Now add today's games to the rolling history
        for g in date_games:
            home = g["home_team"]
            away = g["away_team"]
            home_win = g.get("home_win", False)
            h_gf = g.get("home_score", 0)
            h_ga = g.get("away_score", 0)

            if home not in team_history:
                team_history[home] = deque(maxlen=n)
            team_history[home].append((1 if home_win else 0, h_gf, h_ga))

            if away not in team_history:
                team_history[away] = deque(maxlen=n)
            team_history[away].append((0 if home_win else 1, h_ga, h_gf))

    return form_index


# Module-level cache for form index to avoid recomputation across calls
_form_index_cache = {}
_form_index_games_id = None


def _get_form_index(all_games: list) -> dict:
    """Get or build the form index, cached by game list identity."""
    global _form_index_cache, _form_index_games_id
    games_id = id(all_games)
    if games_id != _form_index_games_id:
        _form_index_cache = _build_form_index(all_games)
        _form_index_games_id = games_id
    return _form_index_cache


def find_similar_games(
    home_team: str,
    away_team: str,
    standings: dict,
    all_games: list,
    team_forms: dict,
    n_similar: int = 50,
    min_similarity: float = 0.55,
) -> list:
    """
    Find the N most similar historical games to the current matchup.
    Returns list of (game, similarity_score) tuples.

    Uses pre-indexed point-in-time form data (O(n) build, O(1) lookup)
    instead of per-game O(n) scans. Total complexity: O(n) vs O(n*m).
    """
    home_standing = standings.get(home_team, {})
    away_standing = standings.get(away_team, {})
    home_form = team_forms.get(home_team, {"win_pct": 0.5, "avg_gf": 3.0, "avg_ga": 3.0})
    away_form = team_forms.get(away_team, {"win_pct": 0.5, "avg_gf": 3.0, "avg_ga": 3.0})

    # Current matchup stats: blend standings and recent form
    home_stats = {
        "win_pct": 0.4 * home_standing.get("win_pct", 0.5) + 0.6 * home_form.get("win_pct", 0.5),
        "avg_gf": 0.4 * home_standing.get("goals_for_pg", 3.0) + 0.6 * home_form.get("avg_gf", 3.0),
        "avg_ga": 0.4 * home_standing.get("goals_against_pg", 3.0) + 0.6 * home_form.get("avg_ga", 3.0),
        "points_pct": home_standing.get("points_pct", 0.5),
    }
    away_stats = {
        "win_pct": 0.4 * away_standing.get("win_pct", 0.5) + 0.6 * away_form.get("win_pct", 0.5),
        "avg_gf": 0.4 * away_standing.get("goals_for_pg", 3.0) + 0.6 * away_form.get("avg_gf", 3.0),
        "avg_ga": 0.4 * away_standing.get("goals_against_pg", 3.0) + 0.6 * away_form.get("avg_ga", 3.0),
        "points_pct": away_standing.get("points_pct", 0.5),
    }

    # Get pre-computed form index (built once, O(1) lookups)
    form_index = _get_form_index(all_games)
    default_form = {"win_pct": 0.5, "avg_gf": 3.0, "avg_ga": 3.0, "points_pct": 0.5}

    scored_games = []

    # Time-decay: recent games are more relevant than old ones
    from datetime import datetime
    today = datetime.now()

    for game in all_games:
        game_date = game.get("date", "")
        if not game_date:
            continue

        hist_home = game["home_team"]
        hist_away = game["away_team"]

        # O(1) lookup from pre-built index
        hist_home_stats = form_index.get((hist_home, game_date), default_form)
        hist_away_stats = form_index.get((hist_away, game_date), default_form)

        h2h = {"games": 0}

        similarity = calculate_similarity(
            home_stats, away_stats,
            hist_home_stats, hist_away_stats,
            h2h, game,
            home_team, away_team,
        )

        # Apply time-decay: half-life of 45 days
        # A game from 45 days ago gets 90% of its similarity score
        try:
            game_dt = datetime.strptime(game_date, "%Y-%m-%d")
            days_ago = (today - game_dt).days
            recency_factor = 0.8 + 0.2 * (0.5 ** (days_ago / 45.0))  # Range: [0.8, 1.0]
            similarity *= recency_factor
        except ValueError:
            pass

        if similarity >= min_similarity:
            scored_games.append((game, similarity))

    # Sort by similarity descending
    scored_games.sort(key=lambda x: x[1], reverse=True)
    return scored_games[:n_similar]


def estimate_probabilities(
    similar_games: list,
    home_team: str,
    away_team: str,
    total_line: Optional[float] = None,
    spread_line: Optional[float] = None,
) -> dict:
    """
    From similar historical games, estimate:
    - Home win probability
    - Expected total goals
    - Spread coverage probability
    Uses similarity-weighted averages.
    """
    if not similar_games:
        return {
            "home_win_prob": 0.5,
            "away_win_prob": 0.5,
            "expected_total": 6.0,
            "over_prob": 0.5,
            "under_prob": 0.5,
            "home_cover_prob": 0.5,
            "n_games": 0,
            "confidence": 0.0,
        }

    total_weight = 0
    weighted_home_wins = 0
    weighted_total_goals = 0
    weighted_overs = 0
    weighted_home_covers = 0
    goal_totals = []

    for game, similarity in similar_games:
        weight = similarity ** 2  # Square to emphasize more similar games
        total_weight += weight

        # Home win (in the context of the similar game)
        if game.get("home_win"):
            weighted_home_wins += weight

        # Total goals
        total_goals = game.get("total_goals", 0)
        weighted_total_goals += weight * total_goals
        goal_totals.append(total_goals)

        # Over/under
        if total_line is not None and total_goals > total_line:
            weighted_overs += weight
        elif total_line is not None and total_goals == total_line:
            weighted_overs += weight * 0.5  # Push

        # Spread coverage
        if spread_line is not None:
            goal_diff = game.get("goal_diff", 0)
            if goal_diff + spread_line > 0:
                weighted_home_covers += weight
            elif goal_diff + spread_line == 0:
                weighted_home_covers += weight * 0.5

    if total_weight == 0:
        total_weight = 1

    home_win_prob = weighted_home_wins / total_weight
    expected_total = weighted_total_goals / total_weight

    # Use Poisson distribution for totals — more accurate than raw counts,
    # especially for alternate lines where historical sample is thin.
    # Blend Poisson estimate with empirical data (70/30) when we have enough games.
    if total_line is None:
        total_line = round(expected_total * 2) / 2  # Round to nearest 0.5

    poisson_over = _poisson_over_prob(expected_total, total_line)

    if len(similar_games) >= 20:
        empirical_over = weighted_overs / total_weight if total_weight > 0 else 0.5
        over_prob = 0.7 * poisson_over + 0.3 * empirical_over
    else:
        over_prob = poisson_over

    home_cover_prob = weighted_home_covers / total_weight if spread_line is not None else 0.5

    # Confidence from multiple independent signals, designed for meaningful spread.
    # Target range: ~0.45 to ~0.92, with most games spread across 0.55-0.85.
    avg_similarity = sum(s for _, s in similar_games) / len(similar_games)
    top5_avg = sum(s for _, s in similar_games[:5]) / min(5, len(similar_games))
    high_sim_count = sum(1 for _, s in similar_games if s > 0.75)
    exact_matchups = sum(1 for g, _ in similar_games
                         if g["home_team"] == home_team and g["away_team"] == away_team)
    reverse_matchups = sum(1 for g, _ in similar_games
                           if g["home_team"] == away_team and g["away_team"] == home_team)

    # Similarity scores cluster ~0.82-0.92, so rescale to spread the range.
    # Map [0.75, 0.95] -> [0.0, 1.0] for more dynamic range.
    rescaled_top5 = max(0, min(1, (top5_avg - 0.75) / 0.20))
    rescaled_avg = max(0, min(1, (avg_similarity - 0.70) / 0.20))

    # Similarity spread: low std = consistent matches = higher confidence
    sim_scores = [s for _, s in similar_games]
    sim_std = (sum((s - avg_similarity) ** 2 for s in sim_scores) / len(sim_scores)) ** 0.5
    consistency = max(0, 1.0 - sim_std * 10)  # std of 0.10 -> 0, std of 0.0 -> 1.0

    # 1. Match quality (0-0.25): how good are the top matches?
    quality_conf = 0.25 * rescaled_top5

    # 2. Match volume (0-0.15): how many strong matches exist?
    #    Use diminishing returns: 5 good matches = 0.08, 15 = 0.13, 25+ = 0.15
    volume_conf = 0.15 * min(1.0, (high_sim_count / 10) ** 0.5)

    # 3. Consistency (0-0.15): are similarity scores tightly clustered?
    consistency_conf = 0.15 * consistency

    # 4. Exact matchup history (0-0.20): have these teams actually played?
    h2h_total = exact_matchups + reverse_matchups
    exact_conf = 0.20 * min(1.0, exact_matchups / 3)  # Caps at 3 exact matchups
    # Partial credit for reverse matchups (same teams, different home/away)
    if exact_matchups == 0 and reverse_matchups > 0:
        exact_conf = 0.10 * min(1.0, reverse_matchups / 3)

    # 5. Prediction decisiveness (0-0.15): how far from 50/50 is the model?
    #    A strong lean means the similar games agree on a direction.
    decisiveness = abs(home_win_prob - 0.5) * 2  # 0 at 50/50, 1 at 100/0
    decisive_conf = 0.15 * min(1.0, decisiveness / 0.4)  # Caps at 70/30 split

    # 6. Overall match depth (0-0.05): rescaled average across all games
    depth_conf = 0.05 * rescaled_avg

    confidence = min(0.95, quality_conf + volume_conf + consistency_conf
                     + exact_conf + decisive_conf + depth_conf)

    # Calibrate: map raw confidence to a useful range.
    # Display confidence uses a wider range for meaningful differentiation.
    # Regression strength is separate — we don't want low display confidence
    # to over-regress predictions toward 50/50.
    calibrated_confidence = 0.25 + 0.65 * confidence  # Maps [0, 0.95] -> [0.25, 0.87]

    # Regression uses a higher floor so predictions stay meaningful.
    # Even at low confidence, we trust the model somewhat (floor 0.55).
    regression_strength = 0.55 + 0.40 * confidence  # Maps [0, 0.95] -> [0.55, 0.93]

    # Apply regression to the mean based on regression strength (not display confidence)
    # Low confidence -> pull toward 50/50, high confidence -> trust the model
    regressed_home_prob = home_win_prob * regression_strength + 0.5 * (1 - regression_strength)
    regressed_over_prob = over_prob * regression_strength + 0.5 * (1 - regression_strength)
    # Spreads are harder to predict — extra regression
    spread_conf = regression_strength * 0.6
    regressed_cover_prob = home_cover_prob * spread_conf + 0.5 * (1 - spread_conf)

    # Constraint: cover prob can never exceed win prob (can't cover -1.5 more than you win)
    regressed_cover_prob = min(regressed_cover_prob, regressed_home_prob)
    # Same for away: away cover can't exceed away win prob
    away_cover = 1 - regressed_cover_prob
    away_win = 1 - regressed_home_prob
    if away_cover > away_win:
        regressed_cover_prob = 1 - away_win  # Cap away cover at away win prob

    return {
        "home_win_prob": regressed_home_prob,
        "away_win_prob": 1 - regressed_home_prob,
        "expected_total": expected_total,
        "over_prob": regressed_over_prob,
        "under_prob": 1 - regressed_over_prob,
        "home_cover_prob": regressed_cover_prob,
        "away_cover_prob": 1 - regressed_cover_prob,
        "total_line": total_line,
        "spread_line": spread_line,
        "n_games": len(similar_games),
        "avg_similarity": avg_similarity,
        "confidence": calibrated_confidence,
        "raw_confidence": confidence,
        "raw_home_win_prob": home_win_prob,
        "raw_over_prob": over_prob,
        "goal_distribution": _goal_distribution(goal_totals),
    }


def _poisson_pmf(k: int, mu: float) -> float:
    """Poisson probability mass function: P(X=k) given mean mu."""
    if mu <= 0:
        return 1.0 if k == 0 else 0.0
    return (mu ** k) * math.exp(-mu) / math.factorial(k)


def _poisson_over_prob(expected_total: float, line: float) -> float:
    """
    Calculate P(total > line) using Poisson distribution.
    Handles half-goals (no push) and whole-goals (push = half credit).
    """
    # Sum P(X=0) + P(X=1) + ... + P(X=floor(line))
    is_half = (line % 1) != 0
    floor_line = int(math.floor(line))

    cum_prob = 0.0
    for k in range(floor_line + 1):
        cum_prob += _poisson_pmf(k, expected_total)

    if is_half:
        # Line like 5.5 — over means >= 6
        over_prob = 1.0 - cum_prob
    else:
        # Line like 6.0 — exactly 6 is a push (half credit)
        exact_prob = _poisson_pmf(int(line), expected_total)
        over_prob = 1.0 - cum_prob + exact_prob * 0.5

    return max(0.001, min(0.999, over_prob))


def _goal_distribution(totals: list) -> dict:
    """Simple distribution of total goals in similar games."""
    if not totals:
        return {}
    dist = {}
    for t in totals:
        dist[t] = dist.get(t, 0) + 1
    for k in dist:
        dist[k] = dist[k] / len(totals)
    return dict(sorted(dist.items()))


def blend_model_and_market(
    model_probs: dict,
    market_probs: dict,
    model_weight: float = 0.65,
) -> dict:
    """
    Blend our model's probabilities with market consensus.

    Model weight increased to 0.65 (from 0.55) to give the model more say.
    With recency-weighted training and daily retrains, the model should be
    more responsive to current conditions.

    Confidence scaling uses cbrt for gentler curve.
    """
    confidence = model_probs.get("confidence", 0)

    # Scale model weight by confidence using cube root for gentler scaling
    # At confidence 0.65: sqrt=0.81 vs cbrt=0.87 — less penalty
    # At confidence 0.95: sqrt=0.97 vs cbrt=0.98 — nearly identical
    effective_weight = model_weight * (confidence ** (1/3))

    blended = {}

    # Moneyline
    blended["home_win_prob"] = (
        effective_weight * model_probs["home_win_prob"] +
        (1 - effective_weight) * market_probs.get("home_win_prob", 0.5)
    )
    blended["away_win_prob"] = 1 - blended["home_win_prob"]

    # Totals
    blended["over_prob"] = (
        effective_weight * model_probs["over_prob"] +
        (1 - effective_weight) * market_probs.get("over_prob", 0.5)
    )
    blended["under_prob"] = 1 - blended["over_prob"]

    # Spread — slightly lower weight since spreads are harder to predict
    spread_weight = effective_weight * 0.8
    blended["home_cover_prob"] = (
        spread_weight * model_probs.get("home_cover_prob", 0.5) +
        (1 - spread_weight) * market_probs.get("spread_home_cover_prob", 0.5)
    )
    blended["away_cover_prob"] = 1 - blended["home_cover_prob"]

    # Constraint: cover prob can never exceed win prob
    blended["home_cover_prob"] = min(blended["home_cover_prob"], blended["home_win_prob"])
    blended["away_cover_prob"] = min(blended["away_cover_prob"], blended["away_win_prob"])

    blended["expected_total"] = model_probs.get("expected_total", 6.0)
    blended["model_confidence"] = confidence
    blended["effective_model_weight"] = effective_weight

    return blended
