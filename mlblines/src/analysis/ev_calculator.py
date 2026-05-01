"""
MLB Expected Value Calculator
Compares model probabilities to bookmaker odds to find +EV bets.
Adapted from NHL version with MLB-specific adjustments:
- Skip whole-number run totals (push risk)
- Default 3% min edge (conservative)
- Exclude sharp books by default
"""

from src.data.odds_fetcher import american_to_decimal, american_to_implied_prob
from src.models.model import _poisson_over_prob

# Soft books (model can find edge)
SOFT_BOOKS = {
    "espnbet", "betmgm", "bovada", "ballybet", "draftkings",
    "betrivers", "pointsbet", "bet365", "betway",
    "williamhill_us", "unibet_us", "superbook", "twinspires",
    "wynnbet", "hardrockbet", "fanatics",
}
# Sharp books (no model edge)
SHARP_BOOKS = {
    "fanduel", "betparx", "lowvig", "fliff", "pinnacle", "betcris",
}


def calculate_ev(true_prob, american_odds, stake=1.00):
    """
    Calculate expected value of a bet.
    EV = (P_win * profit) - (P_lose * stake)
    """
    decimal_odds = american_to_decimal(american_odds)
    implied_prob = american_to_implied_prob(american_odds)

    profit_if_win = stake * (decimal_odds - 1)
    loss_if_lose = stake

    ev = (true_prob * profit_if_win) - ((1 - true_prob) * loss_if_lose)
    roi = ev / stake
    edge = true_prob - implied_prob

    return {
        "ev": ev,
        "roi": roi,
        "edge": edge,
        "true_prob": true_prob,
        "implied_prob": implied_prob,
        "american_odds": american_odds,
        "decimal_odds": decimal_odds,
        "stake": stake,
        "profit_if_win": profit_if_win,
        "loss_if_lose": loss_if_lose,
        "is_positive_ev": ev > 0,
    }


def evaluate_all_bets(
    game_label, home_team, away_team,
    blended_probs, best_odds,
    stake=0.50, min_edge=0.03,
    min_confidence=0.40,
    conservative=True,
    totals_only=True,
    # Cap edges at 10%. 10%+ edge bucket on MLB moneylines went 0/6 historically —
    # these are systematically model overconfidence, not real +EV. A 10% edge
    # vs a soft book is already exceptional; anything larger is noise.
    max_edge=0.10,
    book_filter="soft",
):
    """
    Evaluate all possible bets for a single MLB game.
    Conservative mode: moneylines + totals only, 3%+ edge, skip whole-number totals.
    """
    bets = []
    confidence = blended_probs.get("model_confidence", 0)

    if conservative:
        min_edge = max(min_edge, 0.03)
        min_confidence = max(min_confidence, 0.40)

    if confidence < min_confidence:
        return bets

    # Explicit soft-book allowlist. Previous "not in SHARP_BOOKS" logic allowed
    # unknown offshore books (betonlineag, betus, mybookieag) through, which had
    # 35% WR on MLB moneylines. Require known soft-book membership.
    def _book_allowed(book_key):
        if book_filter == "all":
            return book_key.lower() not in SHARP_BOOKS
        return book_key.lower() in SOFT_BOOKS

    # Totals at 54.5% WR get a lower threshold (2.5%) to capture more volume.
    total_min_edge = min(min_edge, 0.025)

    # --- MONEYLINE BETS ---
    # Disabled (totals_only=True by default). ML historical WR was 33% —
    # model has no demonstrable edge on game winners. Re-enable if WR recovers.
    if not totals_only:
        ml_fav_min_edge = max(min_edge, 0.07)
        ml_dog_min_edge = max(min_edge, 0.08)
        home_ml_bet = None
        away_ml_bet = None

        if best_odds["moneyline"]["home"] and _book_allowed(best_odds["moneyline"]["home"]["book"]):
            home_odds = best_odds["moneyline"]["home"]["price"]
            required_edge = ml_dog_min_edge if home_odds > 0 else ml_fav_min_edge
            ev_data = calculate_ev(blended_probs["home_win_prob"], home_odds, stake)
            if required_edge <= ev_data["edge"] <= max_edge:
                home_ml_bet = {
                    "game": game_label,
                    "bet_type": "Moneyline",
                    "pick": f"{home_team} ML",
                    "book": best_odds["moneyline"]["home"]["book"],
                    "odds": home_odds,
                    **ev_data,
                    "confidence": confidence,
                }

        if best_odds["moneyline"]["away"] and _book_allowed(best_odds["moneyline"]["away"]["book"]):
            away_odds = best_odds["moneyline"]["away"]["price"]
            required_edge = ml_dog_min_edge if away_odds > 0 else ml_fav_min_edge
            ev_data = calculate_ev(blended_probs["away_win_prob"], away_odds, stake)
            if required_edge <= ev_data["edge"] <= max_edge:
                away_ml_bet = {
                    "game": game_label,
                    "bet_type": "Moneyline",
                    "pick": f"{away_team} ML",
                    "book": best_odds["moneyline"]["away"]["book"],
                    "odds": away_odds,
                    **ev_data,
                    "confidence": confidence,
                }

        if home_ml_bet and away_ml_bet:
            bets.append(home_ml_bet if home_ml_bet["edge"] > away_ml_bet["edge"] else away_ml_bet)
        elif home_ml_bet:
            bets.append(home_ml_bet)
        elif away_ml_bet:
            bets.append(away_ml_bet)

    # --- RUN LINE (SPREAD) BETS ---
    # Skip in conservative mode (run lines are harder to predict in baseball)
    if not conservative:
        home_spread = None
        away_spread = None

        if best_odds["spread"]["home"] and _book_allowed(best_odds["spread"]["home"]["book"]):
            ev_data = calculate_ev(blended_probs["home_cover_prob"],
                                   best_odds["spread"]["home"]["price"], stake)
            if ev_data["edge"] >= min_edge:
                home_spread = {
                    "game": game_label,
                    "bet_type": "Run Line",
                    "pick": f"{home_team} {best_odds['spread']['home']['point']:+.1f}",
                    "book": best_odds["spread"]["home"]["book"],
                    "odds": best_odds["spread"]["home"]["price"],
                    **ev_data,
                    "confidence": confidence * 0.6,
                }

        if best_odds["spread"]["away"] and _book_allowed(best_odds["spread"]["away"]["book"]):
            ev_data = calculate_ev(blended_probs["away_cover_prob"],
                                   best_odds["spread"]["away"]["price"], stake)
            if ev_data["edge"] >= min_edge:
                away_spread = {
                    "game": game_label,
                    "bet_type": "Run Line",
                    "pick": f"{away_team} {best_odds['spread']['away']['point']:+.1f}",
                    "book": best_odds["spread"]["away"]["book"],
                    "odds": best_odds["spread"]["away"]["price"],
                    **ev_data,
                    "confidence": confidence * 0.6,
                }

        if home_spread and away_spread:
            bets.append(home_spread if home_spread["edge"] > away_spread["edge"] else away_spread)
        elif home_spread:
            bets.append(home_spread)
        elif away_spread:
            bets.append(away_spread)

    # --- TOTAL BETS ---
    expected_total = blended_probs.get("expected_total",
                                       best_odds["total"]["over"]["point"] if best_odds["total"]["over"] else 9.0)

    best_total_bet = None
    all_total_lines = set()
    all_books = best_odds.get("all_books", {})

    for bk, bk_odds in all_books.items():
        if "total_over" in bk_odds:
            all_total_lines.add((bk, "over", bk_odds["total_over"]["point"], bk_odds["total_over"]["price"]))
        if "total_under" in bk_odds:
            all_total_lines.add((bk, "under", bk_odds["total_under"]["point"], bk_odds["total_under"]["price"]))

    if best_odds["total"]["over"]:
        all_total_lines.add((best_odds["total"]["over"]["book"], "over",
                             best_odds["total"]["over"]["point"], best_odds["total"]["over"]["price"]))
    if best_odds["total"]["under"]:
        all_total_lines.add((best_odds["total"]["under"]["book"], "under",
                             best_odds["total"]["under"]["point"], best_odds["total"]["under"]["price"]))

    for book, side, point, price in all_total_lines:
        if not _book_allowed(book):
            continue

        # SKIP whole-number run totals — they push, which the EV calc doesn't handle
        if point == int(point):
            continue

        poisson_over = _poisson_over_prob(expected_total, point)

        primary_line = best_odds["total"]["over"]["point"] if best_odds["total"]["over"] else None
        if primary_line and abs(point - primary_line) < 0.1:
            true_prob = blended_probs["over_prob"] if side == "over" else blended_probs["under_prob"]
        else:
            true_prob = poisson_over if side == "over" else (1.0 - poisson_over)

        ev_data = calculate_ev(true_prob=true_prob, american_odds=price, stake=stake)

        # Under bets need higher edge (model tends to have under bias)
        effective_min_edge = total_min_edge * 1.5 if side == "under" else total_min_edge

        if ev_data["edge"] >= effective_min_edge and ev_data["edge"] <= max_edge:
            candidate = {
                "game": game_label,
                "bet_type": "Total",
                "pick": f"{'Over' if side == 'over' else 'Under'} {point}",
                "book": book,
                "odds": price,
                **ev_data,
                "confidence": confidence,
            }
            if best_total_bet is None or candidate["ev"] > best_total_bet["ev"]:
                best_total_bet = candidate

    if best_total_bet:
        bets.append(best_total_bet)

    # Add Kelly stake sizing
    for bet in bets:
        kelly_frac = kelly_criterion(bet["true_prob"], bet["decimal_odds"], fraction=0.25)
        bet["kelly_fraction"] = kelly_frac
        bet["kelly_stake"] = round(kelly_frac * 100, 2)

    bets.sort(key=lambda b: b["ev"], reverse=True)
    return bets


def format_recommendations(all_bets, top_n=15, quota_info=None):
    """Format top bet recommendations into a readable report."""
    if not all_bets:
        return "No +EV bets found for today's games."

    all_bets.sort(key=lambda b: b["ev"], reverse=True)
    top = all_bets[:top_n]

    lines = []
    lines.append("=" * 75)
    lines.append("  MLB +EV BET RECOMMENDATIONS")
    lines.append("=" * 75)
    lines.append("")
    lines.append(f"  Found {len(all_bets)} total +EV bets, showing top {min(top_n, len(all_bets))}:")
    lines.append("")

    for i, bet in enumerate(top, 1):
        edge_pct = bet["edge"]
        if edge_pct >= 0.07:
            grade = "A  "
        elif edge_pct >= 0.04:
            grade = "B+ "
        elif edge_pct >= 0.03:
            grade = "B  "
        else:
            grade = "C+ "
        lines.append(f"  {i}. [{grade}] {bet['pick']}")
        lines.append(f"     Game: {bet['game']}")
        lines.append(f"     Type: {bet['bet_type']} | Book: {bet['book']}")
        lines.append(f"     Odds: {bet['odds']:+d} (decimal: {bet['decimal_odds']:.3f})")
        lines.append(f"     Model prob: {bet['true_prob']:.1%} vs Implied: {bet['implied_prob']:.1%}")
        lines.append(f"     Edge: {bet['edge']:.1%} | EV per $1: ${bet['ev']:.4f} | ROI: {bet['roi']:.2%}")
        kelly_pct = bet.get('kelly_stake', 0)
        lines.append(f"     Confidence: {bet['confidence']:.0%} | Kelly: {kelly_pct:.1f}% of bankroll")
        lines.append("")

    total_ev = sum(b["ev"] for b in top)
    avg_edge = sum(b["edge"] for b in top) / len(top)
    total_stake = sum(b["stake"] for b in top)

    lines.append("-" * 75)
    lines.append(f"  SUMMARY (top {len(top)} bets)")
    lines.append(f"  Total stake: ${total_stake:.2f}")
    lines.append(f"  Total expected profit: ${total_ev:.4f}")
    lines.append(f"  Average edge: {avg_edge:.2%}")
    lines.append(f"  Expected ROI: {total_ev/total_stake:.2%}")
    lines.append("=" * 75)
    lines.append("")
    lines.append("  EDGE GRADES:")
    lines.append("    A  = 7%+  exceptional (rare, verify before betting)")
    lines.append("    B+ = 4-7% very good")
    lines.append("    B  = 3-4% solid (sharp bettor territory)")
    lines.append("    C+ = 2-3% thin but playable at volume")
    lines.append("")

    if quota_info:
        lines.append("-" * 75)
        lines.append("  ODDS API QUOTA")
        if isinstance(quota_info, dict) and "total_keys" in quota_info:
            lines.append(f"  Total API keys: {quota_info['total_keys']}")
            lines.append(f"  Combined quota: {quota_info['total_used']} used, {quota_info['total_remaining']} remaining")
        lines.append("=" * 75)
        lines.append("")

    return "\n".join(lines)


def generate_parlays(recommendations: list, max_legs: int = 2, stake: float = 0.50) -> list:
    """
    Generate parlay combinations from the day's best straight bets.

    Historical MLB parlay performance was catastrophic (3-leg: 6W/115L = 5% WR,
    -60% ROI; 2-leg: 5W/17L = 23% WR, -10% ROI). Root cause: the ML leg pool had
    a 33% straight-bet WR, so 3-leg combinations of ML picks compounded the loss.

    Post-fix constraints:
      - 2 legs maximum (3-leg explosion removed)
      - Totals (Overs only, 54% straight-bet WR) are preferred legs
      - ML legs require 5%+ edge (up from 3%) and confidence >= 0.50
      - Max 3 parlays per day, sorted by EV
      - No two legs from the same game
    """
    from itertools import combinations

    # Totals-only parlays (MLs disabled — 33% WR, no demonstrated edge).
    # Overs preferred; Unders allowed if edge is strong (4%+).
    overs = [
        b for b in recommendations
        if b["bet_type"] == "Total"
        and "Over" in b.get("pick", "")
        and b["edge"] >= 0.03
        and b["confidence"] >= 0.40
    ]

    unders = [
        b for b in recommendations
        if b["bet_type"] == "Total"
        and "Under" in b.get("pick", "")
        and b["edge"] >= 0.04
        and b["confidence"] >= 0.40
    ]

    eligible = overs + unders
    if len(eligible) < 2:
        return []

    # Hard cap at 2 legs regardless of caller request
    effective_max_legs = min(max_legs, 2)

    parlays = []
    for n_legs in range(2, min(effective_max_legs + 1, len(eligible) + 1)):
        for combo in combinations(eligible, n_legs):
            # No same-game parlays at all: baseball outcomes within a game are
            # correlated (high-scoring game -> Over + home team often) which
            # inflates the independent-legs parlay EV calculation.
            seen_games = set()
            skip = False
            for leg in combo:
                if leg["game"] in seen_games:
                    skip = True
                    break
                seen_games.add(leg["game"])
            if skip:
                continue

            combined_decimal = 1.0
            combined_true_prob = 1.0
            combined_implied_prob = 1.0
            for leg in combo:
                combined_decimal *= leg["decimal_odds"]
                combined_true_prob *= leg["true_prob"]
                combined_implied_prob *= leg["implied_prob"]

            payout = stake * (combined_decimal - 1)
            ev = (combined_true_prob * payout) - ((1 - combined_true_prob) * stake)
            roi = ev / stake
            edge = combined_true_prob - combined_implied_prob

            if combined_decimal >= 2.0:
                combined_american = int(round((combined_decimal - 1) * 100))
            else:
                combined_american = int(round(-100 / (combined_decimal - 1)))

            from datetime import datetime
            parlays.append({
                "legs": [
                    {
                        "pick": leg["pick"], "game": leg["game"],
                        "odds": leg["odds"], "decimal_odds": leg["decimal_odds"],
                        "true_prob": leg["true_prob"], "implied_prob": leg["implied_prob"],
                        "edge": leg["edge"], "bet_type": leg["bet_type"], "book": leg["book"],
                    }
                    for leg in combo
                ],
                "n_legs": n_legs,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "datetime": datetime.now().isoformat(timespec="seconds"),
                "combined_odds": combined_american,
                "combined_decimal": round(combined_decimal, 3),
                "combined_true_prob": round(combined_true_prob, 4),
                "combined_implied_prob": round(combined_implied_prob, 4),
                "ev": round(ev, 4),
                "roi": round(roi, 4),
                "edge": round(edge, 4),
                "payout": round(stake * combined_decimal, 2),
                "stake": stake,
            })

    parlays.sort(key=lambda p: p["ev"], reverse=True)
    # Cap at 3 per day (down from 10) to reduce exposure given historical
    # parlay drawdown — fewer, higher-quality parlays
    return parlays[:3]


def kelly_criterion(true_prob, decimal_odds, fraction=0.25):
    """
    Kelly criterion for optimal bet sizing.
    Uses fractional Kelly (default 1/4) for safety.
    """
    b = decimal_odds - 1
    p = true_prob
    q = 1 - p
    full_kelly = (b * p - q) / b
    if full_kelly <= 0:
        return 0.0
    return full_kelly * fraction
