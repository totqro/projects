"""
MLB Historical Similarity Model
Compares current matchups to similar historical games to estimate
true win probabilities, expected total runs, and run line coverage.
"""

import math
from typing import Optional
from collections import deque


def calculate_similarity(
    home_stats, away_stats,
    hist_home_stats, hist_away_stats,
    hist_game, current_home, current_away,
):
    """
    Calculate how similar a historical game is to the current matchup.
    Baseball-specific: weighs pitching quality, run scoring, and matchup context.
    """
    score = 0.0
    max_score = 0.0

    # 1. Team quality differential (weight: 3)
    weight = 3.0
    max_score += weight
    current_diff = home_stats.get("win_pct", 0.5) - away_stats.get("win_pct", 0.5)
    hist_diff = hist_home_stats.get("win_pct", 0.5) - hist_away_stats.get("win_pct", 0.5)
    quality_sim = 1.0 - min(abs(current_diff - hist_diff), 1.0)
    score += weight * quality_sim

    # 2. Home run scoring similarity (weight: 2)
    weight = 2.0
    max_score += weight
    current_rs = home_stats.get("avg_rs", 4.5)
    hist_rs = hist_home_stats.get("avg_rs", 4.5)
    rs_sim = 1.0 - min(abs(current_rs - hist_rs) / 5.0, 1.0)
    score += weight * rs_sim

    # 3. Away run scoring similarity (weight: 2)
    weight = 2.0
    max_score += weight
    current_rs2 = away_stats.get("avg_rs", 4.5)
    hist_rs2 = hist_away_stats.get("avg_rs", 4.5)
    rs_sim2 = 1.0 - min(abs(current_rs2 - hist_rs2) / 5.0, 1.0)
    score += weight * rs_sim2

    # 4. Home run allowed similarity (weight: 2)
    weight = 2.0
    max_score += weight
    current_ra = home_stats.get("avg_ra", 4.5)
    hist_ra = hist_home_stats.get("avg_ra", 4.5)
    ra_sim = 1.0 - min(abs(current_ra - hist_ra) / 5.0, 1.0)
    score += weight * ra_sim

    # 5. Away run allowed similarity (weight: 2)
    weight = 2.0
    max_score += weight
    current_ra2 = away_stats.get("avg_ra", 4.5)
    hist_ra2 = hist_away_stats.get("avg_ra", 4.5)
    ra_sim2 = 1.0 - min(abs(current_ra2 - hist_ra2) / 5.0, 1.0)
    score += weight * ra_sim2

    # 6. Same teams bonus (weight: 2)
    weight = 2.0
    max_score += weight
    if hist_game["home_team"] == current_home and hist_game["away_team"] == current_away:
        score += weight
    elif hist_game["home_team"] == current_away and hist_game["away_team"] == current_home:
        score += weight * 0.5

    # 7. Run differential similarity (weight: 2)
    weight = 2.0
    max_score += weight
    current_rd = home_stats.get("run_diff_pg", 0) - away_stats.get("run_diff_pg", 0)
    hist_rd = hist_home_stats.get("run_diff_pg", 0) - hist_away_stats.get("run_diff_pg", 0)
    rd_sim = 1.0 - min(abs(current_rd - hist_rd) / 3.0, 1.0)
    score += weight * rd_sim

    return score / max_score if max_score > 0 else 0.0


def _build_form_index(all_games, n=10):
    """Pre-compute point-in-time form for every team at every game date."""
    completed = [
        g for g in all_games
        if g.get("game_state") == "FINAL" and g.get("date")
    ]
    completed.sort(key=lambda g: g["date"])

    team_history = {}
    form_index = {}
    default_form = {"win_pct": 0.5, "avg_rs": 4.5, "avg_ra": 4.5}

    games_by_date = {}
    for g in completed:
        d = g["date"]
        if d not in games_by_date:
            games_by_date[d] = []
        games_by_date[d].append(g)

    for date in sorted(games_by_date.keys()):
        date_games = games_by_date[date]

        for g in date_games:
            for team in (g["home_team"], g["away_team"]):
                if (team, date) not in form_index:
                    history = team_history.get(team)
                    if history and len(history) > 0:
                        wins = sum(r[0] for r in history)
                        rs = sum(r[1] for r in history)
                        ra = sum(r[2] for r in history)
                        ng = len(history)
                        form_index[(team, date)] = {
                            "win_pct": wins / ng,
                            "avg_rs": rs / ng,
                            "avg_ra": ra / ng,
                        }
                    else:
                        form_index[(team, date)] = default_form

        for g in date_games:
            home = g["home_team"]
            away = g["away_team"]
            home_win = g.get("home_win", False)

            if home not in team_history:
                team_history[home] = deque(maxlen=n)
            team_history[home].append((1 if home_win else 0, g.get("home_score", 0), g.get("away_score", 0)))

            if away not in team_history:
                team_history[away] = deque(maxlen=n)
            team_history[away].append((0 if home_win else 1, g.get("away_score", 0), g.get("home_score", 0)))

    return form_index


_form_index_cache = {}
_form_index_games_id = None


def _get_form_index(all_games):
    global _form_index_cache, _form_index_games_id
    games_id = id(all_games)
    if games_id != _form_index_games_id:
        _form_index_cache = _build_form_index(all_games)
        _form_index_games_id = games_id
    return _form_index_cache


def find_similar_games(
    home_team, away_team, standings, all_games, team_forms,
    n_similar=50, min_similarity=0.55,
):
    """Find the N most similar historical games to the current matchup."""
    home_standing = standings.get(home_team, {})
    away_standing = standings.get(away_team, {})
    home_form = team_forms.get(home_team, {"win_pct": 0.5, "avg_rs": 4.5, "avg_ra": 4.5})
    away_form = team_forms.get(away_team, {"win_pct": 0.5, "avg_rs": 4.5, "avg_ra": 4.5})

    home_stats = {
        "win_pct": 0.4 * home_standing.get("win_pct", 0.5) + 0.6 * home_form.get("win_pct", 0.5),
        "avg_rs": 0.4 * home_standing.get("runs_scored_pg", 4.5) + 0.6 * home_form.get("avg_rs", 4.5),
        "avg_ra": 0.4 * home_standing.get("runs_allowed_pg", 4.5) + 0.6 * home_form.get("avg_ra", 4.5),
        "run_diff_pg": home_standing.get("run_diff_pg", 0),
    }
    away_stats = {
        "win_pct": 0.4 * away_standing.get("win_pct", 0.5) + 0.6 * away_form.get("win_pct", 0.5),
        "avg_rs": 0.4 * away_standing.get("runs_scored_pg", 4.5) + 0.6 * away_form.get("avg_rs", 4.5),
        "avg_ra": 0.4 * away_standing.get("runs_allowed_pg", 4.5) + 0.6 * away_form.get("avg_ra", 4.5),
        "run_diff_pg": away_standing.get("run_diff_pg", 0),
    }

    form_index = _get_form_index(all_games)
    default_form = {"win_pct": 0.5, "avg_rs": 4.5, "avg_ra": 4.5, "run_diff_pg": 0}

    scored_games = []
    from datetime import datetime
    today = datetime.now()

    for game in all_games:
        game_date = game.get("date", "")
        if not game_date:
            continue

        hist_home = game["home_team"]
        hist_away = game["away_team"]

        hist_home_stats = form_index.get((hist_home, game_date), default_form)
        hist_away_stats = form_index.get((hist_away, game_date), default_form)

        similarity = calculate_similarity(
            home_stats, away_stats,
            hist_home_stats, hist_away_stats,
            game, home_team, away_team,
        )

        # Time decay: half-life 45 days
        try:
            game_dt = datetime.strptime(game_date, "%Y-%m-%d")
            days_ago = (today - game_dt).days
            recency_factor = 0.8 + 0.2 * (0.5 ** (days_ago / 45.0))
            similarity *= recency_factor
        except ValueError:
            pass

        if similarity >= min_similarity:
            scored_games.append((game, similarity))

    scored_games.sort(key=lambda x: x[1], reverse=True)
    return scored_games[:n_similar]


def _poisson_pmf(k, mu):
    """Poisson probability mass function."""
    if mu <= 0:
        return 1.0 if k == 0 else 0.0
    return (mu ** k) * math.exp(-mu) / math.factorial(k)


def _poisson_over_prob(expected_total, line):
    """
    Calculate P(total > line) using Poisson distribution.
    Handles half-runs (no push) and whole-runs (push = half credit).
    """
    is_half = (line % 1) != 0
    floor_line = int(math.floor(line))

    cum_prob = 0.0
    for k in range(floor_line + 1):
        cum_prob += _poisson_pmf(k, expected_total)

    if is_half:
        over_prob = 1.0 - cum_prob
    else:
        exact_prob = _poisson_pmf(int(line), expected_total)
        over_prob = 1.0 - cum_prob + exact_prob * 0.5

    return max(0.001, min(0.999, over_prob))


def estimate_probabilities(
    similar_games, home_team, away_team,
    total_line=None, spread_line=None,
):
    """
    From similar historical games, estimate:
    - Home win probability
    - Expected total runs
    - Over/under probability
    - Run line coverage probability
    """
    if not similar_games:
        return {
            "home_win_prob": 0.5, "away_win_prob": 0.5,
            "expected_total": 9.0, "over_prob": 0.5, "under_prob": 0.5,
            "home_cover_prob": 0.5, "n_games": 0, "confidence": 0.0,
        }

    total_weight = 0
    weighted_home_wins = 0
    weighted_total_runs = 0
    weighted_overs = 0
    weighted_home_covers = 0
    run_totals = []

    for game, similarity in similar_games:
        weight = similarity ** 2
        total_weight += weight

        if game.get("home_win"):
            weighted_home_wins += weight

        total_runs = game.get("total_runs", 0)
        weighted_total_runs += weight * total_runs
        run_totals.append(total_runs)

        if total_line is not None and total_runs > total_line:
            weighted_overs += weight
        elif total_line is not None and total_runs == total_line:
            weighted_overs += weight * 0.5

        if spread_line is not None:
            run_diff = game.get("run_diff", 0)
            if run_diff + spread_line > 0:
                weighted_home_covers += weight
            elif run_diff + spread_line == 0:
                weighted_home_covers += weight * 0.5

    if total_weight == 0:
        total_weight = 1

    home_win_prob = weighted_home_wins / total_weight
    expected_total = weighted_total_runs / total_weight

    if total_line is None:
        total_line = round(expected_total * 2) / 2

    poisson_over = _poisson_over_prob(expected_total, total_line)
    if len(similar_games) >= 20:
        empirical_over = weighted_overs / total_weight
        over_prob = 0.7 * poisson_over + 0.3 * empirical_over
    else:
        over_prob = poisson_over

    home_cover_prob = weighted_home_covers / total_weight if spread_line is not None else 0.5

    # Confidence scoring
    avg_similarity = sum(s for _, s in similar_games) / len(similar_games)
    top5_avg = sum(s for _, s in similar_games[:5]) / min(5, len(similar_games))
    high_sim_count = sum(1 for _, s in similar_games if s > 0.75)
    exact_matchups = sum(1 for g, _ in similar_games
                         if g["home_team"] == home_team and g["away_team"] == away_team)

    rescaled_top5 = max(0, min(1, (top5_avg - 0.75) / 0.20))
    rescaled_avg = max(0, min(1, (avg_similarity - 0.70) / 0.20))

    sim_scores = [s for _, s in similar_games]
    sim_std = (sum((s - avg_similarity) ** 2 for s in sim_scores) / len(sim_scores)) ** 0.5
    consistency = max(0, 1.0 - sim_std * 10)

    quality_conf = 0.25 * rescaled_top5
    volume_conf = 0.15 * min(1.0, (high_sim_count / 10) ** 0.5)
    consistency_conf = 0.15 * consistency
    exact_conf = 0.20 * min(1.0, exact_matchups / 3)
    decisiveness = abs(home_win_prob - 0.5) * 2
    decisive_conf = 0.15 * min(1.0, decisiveness / 0.4)
    depth_conf = 0.05 * rescaled_avg

    confidence = min(0.95, quality_conf + volume_conf + consistency_conf +
                     exact_conf + decisive_conf + depth_conf)
    calibrated_confidence = 0.25 + 0.65 * confidence
    regression_strength = 0.55 + 0.40 * confidence

    regressed_home_prob = home_win_prob * regression_strength + 0.5 * (1 - regression_strength)
    regressed_over_prob = over_prob * regression_strength + 0.5 * (1 - regression_strength)
    spread_conf = regression_strength * 0.6
    regressed_cover_prob = home_cover_prob * spread_conf + 0.5 * (1 - spread_conf)
    regressed_cover_prob = min(regressed_cover_prob, regressed_home_prob)

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
        "run_distribution": _run_distribution(run_totals),
    }


def _run_distribution(totals):
    if not totals:
        return {}
    dist = {}
    for t in totals:
        dist[t] = dist.get(t, 0) + 1
    for k in dist:
        dist[k] = dist[k] / len(totals)
    return dict(sorted(dist.items()))


def blend_model_and_market(model_probs, market_probs, model_weight=0.65):
    """
    Blend model probabilities with market consensus.
    Confidence scaling uses cube root for gentler curve.
    """
    confidence = model_probs.get("confidence", 0)
    effective_weight = model_weight * (confidence ** (1/3))

    blended = {}
    blended["home_win_prob"] = (
        effective_weight * model_probs["home_win_prob"] +
        (1 - effective_weight) * market_probs.get("home_win_prob", 0.5)
    )
    blended["away_win_prob"] = 1 - blended["home_win_prob"]

    blended["over_prob"] = (
        effective_weight * model_probs["over_prob"] +
        (1 - effective_weight) * market_probs.get("over_prob", 0.5)
    )
    blended["under_prob"] = 1 - blended["over_prob"]

    spread_weight = effective_weight * 0.8
    blended["home_cover_prob"] = (
        spread_weight * model_probs.get("home_cover_prob", 0.5) +
        (1 - spread_weight) * market_probs.get("spread_home_cover_prob", 0.5)
    )
    blended["away_cover_prob"] = 1 - blended["home_cover_prob"]
    blended["home_cover_prob"] = min(blended["home_cover_prob"], blended["home_win_prob"])
    blended["away_cover_prob"] = min(blended["away_cover_prob"], blended["away_win_prob"])

    # Blend expected total with market total line — use reduced model weight
    # for totals since model total predictions are noisier than win predictions
    model_total = model_probs.get("expected_total", 9.0)
    market_total = market_probs.get("total_line", model_total)
    total_model_weight = effective_weight * 0.5  # half the win-prob weight
    blended["expected_total"] = total_model_weight * model_total + (1 - total_model_weight) * market_total
    blended["model_confidence"] = confidence
    blended["effective_model_weight"] = effective_weight

    return blended
