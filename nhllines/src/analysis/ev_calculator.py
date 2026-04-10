"""
Expected Value Calculator
Compares model probabilities to bookmaker odds to find +EV bets.
Outputs ranked recommendations.
"""

from src.data.odds_fetcher import american_to_decimal, american_to_implied_prob
from src.models.model import _poisson_over_prob

# Books where the model has historically had edge (soft/recreational books)
# Based on optimization analysis (144 bets, Mar-Apr 2026):
#   Bovada 78% WR +65% ROI, BetMGM 67% WR +29% ROI, HardRock 67% WR +24% ROI
# Sharp/losing books: BetParx 17% WR -92% ROI, LowVig 29% WR -61% ROI,
#   Betanysports 17% WR -56% ROI, Fliff 20% WR -37% ROI,
#   FanDuel 36% WR -25% ROI, DraftKings 37% WR -24% ROI
SOFT_BOOKS = {
    "espnbet", "betmgm", "bovada", "ballybet",
    "betrivers", "pointsbet", "thescore", "betway", "bet365",
    "williamhill_us", "unibet_us", "superbook", "twinspires",
    "wynnbet", "hardrockbet",
}
SHARP_BOOKS = {
    "fanduel", "betparx", "lowvig", "fliff", "pinnacle", "betcris",
    "draftkings", "betanysports",
}


def calculate_ev(
    true_prob: float,
    american_odds: int,
    stake: float = 1.00,
) -> dict:
    """
    Calculate expected value of a bet.

    EV = (P_win * profit) - (P_lose * stake)
    Where profit = stake * (decimal_odds - 1)

    Returns dict with EV, ROI, and breakdown.
    """
    decimal_odds = american_to_decimal(american_odds)
    implied_prob = american_to_implied_prob(american_odds)

    profit_if_win = stake * (decimal_odds - 1)
    loss_if_lose = stake

    ev = (true_prob * profit_if_win) - ((1 - true_prob) * loss_if_lose)
    roi = ev / stake  # As a fraction

    # Edge = our probability minus the implied probability
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
    game_label: str,
    home_team: str,
    away_team: str,
    blended_probs: dict,
    best_odds: dict,
    stake: float = 1.00,
    min_edge: float = 0.03,  # Minimum 3% edge (optimized: soft books + edge ≥3% = 65% WR)
    min_confidence: float = 0.50,  # Minimum 50% confidence (soft book filter is the real edge)
    conservative: bool = False,
    max_edge: float = 1.0,  # No practical cap - high-edge bets are the most profitable
    book_filter: str = "soft",  # "soft" = exclude sharp books, "all" = no filter
    espn_only: bool = False,  # ESPN Bet only mode
) -> list:
    """
    Evaluate all possible bets for a single game.
    Returns list of bet recommendations sorted by EV.

    conservative mode: only totals and moneylines, higher min edge
    """
    bets = []
    confidence = blended_probs.get("model_confidence", 0)

    # Skip if confidence is too low
    if confidence < min_confidence:
        return bets

    # In conservative mode, raise edge bar but NOT confidence
    # Backtesting showed soft book filter is the real edge driver,
    # not confidence (model rarely exceeds 55% confidence anyway)
    if conservative:
        min_edge = max(min_edge, 0.04)  # At least 4% edge in conservative mode

    # Book filter helper — skip bets on sharp books where model has no edge
    def _book_allowed(book_key: str) -> bool:
        if espn_only:
            return book_key.lower() == "espnbet"
        if book_filter == "all":
            return True
        return book_key.lower() not in SHARP_BOOKS

    # ESPN-only mode: rebuild best_odds using ESPN's actual prices
    # so edge is calculated against ESPN's lines, not best-available
    if espn_only:
        espn_book = best_odds.get("all_books", {}).get("espnbet", {})
        if not espn_book:
            return bets  # ESPN has no odds for this game

        best_odds = dict(best_odds)  # shallow copy
        # Moneyline
        if "ml_home" in espn_book:
            best_odds["moneyline"] = {
                "home": {"price": espn_book["ml_home"], "book": "espnbet"},
                "away": {"price": espn_book.get("ml_away", 0), "book": "espnbet"} if "ml_away" in espn_book else None,
            }
        else:
            best_odds["moneyline"] = {"home": None, "away": None}

        # Totals
        if "total_over" in espn_book:
            over_data = espn_book["total_over"]
            under_data = espn_book.get("total_under", {})
            best_odds["total"] = {
                "over": {"price": over_data["price"], "point": over_data["point"], "book": "espnbet"} if isinstance(over_data, dict) else None,
                "under": {"price": under_data["price"], "point": under_data["point"], "book": "espnbet"} if isinstance(under_data, dict) else None,
            }
        else:
            best_odds["total"] = {"over": None, "under": None}

        # Spread
        if "spread_home" in espn_book:
            home_sp = espn_book["spread_home"]
            away_sp = espn_book.get("spread_away", {})
            best_odds["spread"] = {
                "home": {"price": home_sp["price"], "point": home_sp["point"], "book": "espnbet"} if isinstance(home_sp, dict) else None,
                "away": {"price": away_sp["price"], "point": away_sp["point"], "book": "espnbet"} if isinstance(away_sp, dict) else None,
            }
        else:
            best_odds["spread"] = {"home": None, "away": None}

    # --- MONEYLINE BETS ---
    # Evaluate both but only keep the one with higher edge (if any)
    # Underdogs (positive odds) require higher edge — optimization showed
    # favorites at 64% WR vs underdogs at 39% WR with same edge threshold
    underdog_min_edge = max(min_edge, 0.06)  # Underdogs need 6%+ edge to be profitable
    home_ml_bet = None
    away_ml_bet = None

    if best_odds["moneyline"]["home"] and _book_allowed(best_odds["moneyline"]["home"]["book"]):
        home_odds = best_odds["moneyline"]["home"]["price"]
        required_edge = underdog_min_edge if home_odds > 0 else min_edge
        ev_data = calculate_ev(
            true_prob=blended_probs["home_win_prob"],
            american_odds=home_odds,
            stake=stake,
        )
        if ev_data["edge"] >= required_edge and ev_data["edge"] <= max_edge:
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
        required_edge = underdog_min_edge if away_odds > 0 else min_edge
        ev_data = calculate_ev(
            true_prob=blended_probs["away_win_prob"],
            american_odds=away_odds,
            stake=stake,
        )
        if ev_data["edge"] >= required_edge and ev_data["edge"] <= max_edge:
            away_ml_bet = {
                "game": game_label,
                "bet_type": "Moneyline",
                "pick": f"{away_team} ML",
                "book": best_odds["moneyline"]["away"]["book"],
                "odds": away_odds,
                **ev_data,
                "confidence": confidence,
            }
    
    # Only add the ML bet with higher edge (don't recommend both sides)
    if home_ml_bet and away_ml_bet:
        if home_ml_bet["edge"] > away_ml_bet["edge"]:
            bets.append(home_ml_bet)
        else:
            bets.append(away_ml_bet)
    elif home_ml_bet:
        bets.append(home_ml_bet)
    elif away_ml_bet:
        bets.append(away_ml_bet)

    # --- SPREAD BETS ---
    # Skip spreads entirely in conservative mode (model isn't reliable enough)
    # Spreads use reduced confidence (harder to predict margin than winner)
    spread_confidence = confidence * 0.6
    if not conservative:
        # Evaluate both but only keep the one with higher edge (if any)
        home_spread_bet = None
        away_spread_bet = None

        if best_odds["spread"]["home"]:
            point = best_odds["spread"]["home"]["point"]
            ev_data = calculate_ev(
                true_prob=blended_probs["home_cover_prob"],
                american_odds=best_odds["spread"]["home"]["price"],
                stake=stake,
            )
            if ev_data["edge"] >= min_edge and ev_data["edge"] <= max_edge:
                home_spread_bet = {
                    "game": game_label,
                    "bet_type": "Spread",
                    "pick": f"{home_team} {point:+.1f}",
                    "book": best_odds["spread"]["home"]["book"],
                    "odds": best_odds["spread"]["home"]["price"],
                    **ev_data,
                    "confidence": spread_confidence,
                }

        if best_odds["spread"]["away"]:
            point = best_odds["spread"]["away"]["point"]
            ev_data = calculate_ev(
                true_prob=blended_probs["away_cover_prob"],
                american_odds=best_odds["spread"]["away"]["price"],
                stake=stake,
            )
            if ev_data["edge"] >= min_edge and ev_data["edge"] <= max_edge:
                away_spread_bet = {
                    "game": game_label,
                    "bet_type": "Spread",
                    "pick": f"{away_team} {point:+.1f}",
                    "book": best_odds["spread"]["away"]["book"],
                    "odds": best_odds["spread"]["away"]["price"],
                    **ev_data,
                    "confidence": spread_confidence,
                }
        
        # Only add the spread bet with higher edge (don't recommend both sides)
        if home_spread_bet and away_spread_bet:
            if home_spread_bet["edge"] > away_spread_bet["edge"]:
                bets.append(home_spread_bet)
            else:
                bets.append(away_spread_bet)
        elif home_spread_bet:
            bets.append(home_spread_bet)
        elif away_spread_bet:
            bets.append(away_spread_bet)

    # --- TOTAL BETS ---
    # Use Poisson distribution to evaluate alternate total lines across books.
    # This finds +EV on lines like 5.5 even when the consensus line is 6.5.
    expected_total = blended_probs.get("expected_total",
                                       best_odds["total"]["over"]["point"] if best_odds["total"]["over"] else 6.0)

    best_total_bet = None

    # Collect all unique total lines across all books
    all_total_lines = set()
    all_books = best_odds.get("all_books", {})
    for bk, bk_odds in all_books.items():
        if "total_over" in bk_odds:
            all_total_lines.add((bk, "over", bk_odds["total_over"]["point"], bk_odds["total_over"]["price"]))
        if "total_under" in bk_odds:
            all_total_lines.add((bk, "under", bk_odds["total_under"]["point"], bk_odds["total_under"]["price"]))

    # Also include the best odds entries
    if best_odds["total"]["over"]:
        all_total_lines.add((best_odds["total"]["over"]["book"], "over",
                             best_odds["total"]["over"]["point"], best_odds["total"]["over"]["price"]))
    if best_odds["total"]["under"]:
        all_total_lines.add((best_odds["total"]["under"]["book"], "under",
                             best_odds["total"]["under"]["point"], best_odds["total"]["under"]["price"]))

    for book, side, point, price in all_total_lines:
        if not _book_allowed(book):
            continue
        # Skip .0 lines — they can push (refund), which the EV calc doesn't account for
        if point == int(point):
            continue
        # Calculate Poisson-based probability for this specific line
        poisson_over = _poisson_over_prob(expected_total, point)

        # Blend with the model's over_prob if the line matches the primary line
        primary_line = best_odds["total"]["over"]["point"] if best_odds["total"]["over"] else None
        if primary_line and abs(point - primary_line) < 0.1:
            # Same line as primary — use the blended prob (already Poisson-weighted)
            true_prob = blended_probs["over_prob"] if side == "over" else blended_probs["under_prob"]
        else:
            # Alternate line — use pure Poisson
            true_prob = poisson_over if side == "over" else (1.0 - poisson_over)

        ev_data = calculate_ev(true_prob=true_prob, american_odds=price, stake=stake)

        # Under bets require much higher edge — optimization showed Unders are -18.4% ROI
        # Only take Unders at 7%+ edge (historically profitable band)
        effective_min_edge = max(min_edge, 0.07) if side == "under" else min_edge

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

    # Also evaluate theScore specifically if available
    bets.extend(_evaluate_thescore_odds(
        game_label, home_team, away_team,
        blended_probs, best_odds, stake, min_edge
    ))

    # Add Kelly stake sizing to each bet
    for bet in bets:
        kelly_frac = kelly_criterion(
            bet["true_prob"],
            bet["decimal_odds"],
            fraction=0.25,  # Quarter Kelly for safety
        )
        bet["kelly_fraction"] = kelly_frac
        bet["kelly_stake"] = round(kelly_frac * 100, 2)  # As % of bankroll

    # Sort by EV descending
    bets.sort(key=lambda b: b["ev"], reverse=True)
    return bets


def _evaluate_thescore_odds(
    game_label, home_team, away_team,
    blended_probs, best_odds, stake, min_edge
) -> list:
    """Evaluate bets specifically at theScore Bet odds."""
    bets = []
    thescore = best_odds.get("thescore", {})
    if not thescore:
        return bets

    # theScore moneyline - only keep the side with higher edge
    home_ts_bet = None
    away_ts_bet = None

    if "ml_home" in thescore:
        ev_data = calculate_ev(blended_probs["home_win_prob"], thescore["ml_home"], stake)
        if ev_data["edge"] >= min_edge:
            home_ts_bet = {
                "game": game_label,
                "bet_type": "Moneyline",
                "pick": f"{home_team} ML (theScore)",
                "book": "thescore",
                "odds": thescore["ml_home"],
                **ev_data,
                "confidence": blended_probs.get("model_confidence", 0),
            }

    if "ml_away" in thescore:
        ev_data = calculate_ev(blended_probs["away_win_prob"], thescore["ml_away"], stake)
        if ev_data["edge"] >= min_edge:
            away_ts_bet = {
                "game": game_label,
                "bet_type": "Moneyline",
                "pick": f"{away_team} ML (theScore)",
                "book": "thescore",
                "odds": thescore["ml_away"],
                **ev_data,
                "confidence": blended_probs.get("model_confidence", 0),
            }

    if home_ts_bet and away_ts_bet:
        if home_ts_bet["edge"] > away_ts_bet["edge"]:
            bets.append(home_ts_bet)
        else:
            bets.append(away_ts_bet)
    elif home_ts_bet:
        bets.append(home_ts_bet)
    elif away_ts_bet:
        bets.append(away_ts_bet)

    return bets


def format_recommendations(all_bets: list, top_n: int = 15, quota_info: dict = None) -> str:
    """
    Format the top bet recommendations into a readable report.
    """
    if not all_bets:
        return "No +EV bets found for today's games."

    # Sort all bets across all games by EV
    all_bets.sort(key=lambda b: b["ev"], reverse=True)
    top = all_bets[:top_n]

    lines = []
    lines.append("=" * 75)
    lines.append("  NHL +EV BET RECOMMENDATIONS")
    lines.append("=" * 75)
    lines.append("")
    lines.append(f"  Found {len(all_bets)} total +EV bets, showing top {min(top_n, len(all_bets))}:")
    lines.append("")

    for i, bet in enumerate(top, 1):
        edge_pct = bet["edge"]
        if edge_pct >= 0.07:
            grade = "A  "  # 7%+  exceptional, rare
        elif edge_pct >= 0.04:
            grade = "B+ "  # 4-7% very good
        elif edge_pct >= 0.03:
            grade = "B  "  # 3-4% solid sharp-level edge
        else:
            grade = "C+ "  # 2-3% thin but playable
        lines.append(f"  {i}. [{grade}] {bet['pick']}")
        lines.append(f"     Game: {bet['game']}")
        lines.append(f"     Type: {bet['bet_type']} | Book: {bet['book']}")
        lines.append(f"     Odds: {bet['odds']:+d} (decimal: {bet['decimal_odds']:.3f})")
        lines.append(f"     Model prob: {bet['true_prob']:.1%} vs Implied: {bet['implied_prob']:.1%}")
        lines.append(f"     Edge: {bet['edge']:.1%} | EV per $1: ${bet['ev']:.4f} | ROI: {bet['roi']:.2%}")
        kelly_pct = bet.get('kelly_stake', 0)
        lines.append(f"     Confidence: {bet['confidence']:.0%} | Kelly: {kelly_pct:.1f}% of bankroll")
        lines.append("")

    # Summary stats
    total_ev = sum(b["ev"] for b in top)
    avg_edge = sum(b["edge"] for b in top) / len(top)
    total_stake = sum(b["stake"] for b in top)

    lines.append("-" * 75)
    lines.append(f"  SUMMARY (top {len(top)} bets)")
    lines.append(f"  Total stake: ${total_stake:.2f} CAD")
    lines.append(f"  Total expected profit: ${total_ev:.4f} CAD")
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
    lines.append("  Bet $0.50-$1.00 CAD per pick for optimal bankroll management.")
    lines.append("")
    
    # Add API quota info if available
    if quota_info:
        lines.append("-" * 75)
        lines.append("  ODDS API QUOTA")
        
        # Check if it's the new multi-key format
        if isinstance(quota_info, dict) and "total_keys" in quota_info:
            # Multi-key format
            lines.append(f"  Total API keys: {quota_info['total_keys']}")
            lines.append(f"  Combined quota: {quota_info['total_used']} used, {quota_info['total_remaining']} remaining")
            
            if len(quota_info.get('keys', [])) > 1:
                lines.append("")
                lines.append("  Per-key breakdown:")
                for key_info in quota_info['keys']:
                    lines.append(f"    Key #{key_info['index'] + 1}: {key_info['used']} used, {key_info['remaining']} remaining")
        else:
            # Old single-key format
            lines.append(f"  Requests used this month: {quota_info.get('used', '?')}")
            lines.append(f"  Requests remaining: {quota_info.get('remaining', '?')}")
            if 'last_cost' in quota_info:
                lines.append(f"  Last request cost: {quota_info['last_cost']} credit(s)")
        
        lines.append("=" * 75)
        lines.append("")

    return "\n".join(lines)


def generate_parlays(recommendations: list, max_legs: int = 3, stake: float = 1.00) -> list:
    """
    Generate parlay combinations from the day's best straight bets.

    Focuses on ML favorites (historically 75% WR on ESPN) as parlay legs.
    Generates 2-leg and 3-leg parlays, ranked by expected value.

    Args:
        recommendations: List of straight bet recommendations
        max_legs: Maximum legs per parlay (2 or 3)
        stake: Stake per parlay

    Returns:
        List of parlay dicts sorted by EV
    """
    from itertools import combinations

    # Optimal parlay leg selection based on backtesting (190 parlays, Mar-Apr 2026):
    #   ML fav + pick-ems (<+130) + Overs: 62W-128L, +$59.44, +62.6% ROI, p=0.001
    #   ML fav + Overs only: 40W-85L, +$28.96, +46.3% ROI, p=0.031
    #   Including dogs >+150: ROI drops to +35.8%
    #   All underdogs: -9.3% ROI (kills profitability)

    # ML picks: favorites + pick-ems up to +130 (3%+ edge)
    ml_picks = [
        b for b in recommendations
        if b["bet_type"] == "Moneyline"
        and b["odds"] < 130
        and b["edge"] >= 0.03
        and b["confidence"] >= 0.50
    ]

    # Overs with 3%+ edge
    overs = [
        b for b in recommendations
        if b["bet_type"] == "Total"
        and "Over" in b.get("pick", "")
        and b["edge"] >= 0.03
        and b["confidence"] >= 0.50
    ]

    eligible = ml_picks + overs

    if len(eligible) < 2:
        return []

    parlays = []

    for n_legs in range(2, min(max_legs + 1, len(eligible) + 1)):
        for combo in combinations(eligible, n_legs):
            # Allow same-game parlays but only with different bet types
            # (e.g. ML + Over is fine, but not two MLs from the same game)
            seen_game_types = set()
            skip = False
            for leg in combo:
                key = (leg["game"], leg["bet_type"])
                if key in seen_game_types:
                    skip = True
                    break
                seen_game_types.add(key)
            if skip:
                continue

            # Combined decimal odds = product of individual decimal odds
            combined_decimal = 1.0
            combined_true_prob = 1.0
            combined_implied_prob = 1.0

            for leg in combo:
                combined_decimal *= leg["decimal_odds"]
                combined_true_prob *= leg["true_prob"]
                combined_implied_prob *= leg["implied_prob"]

            # Parlay EV = (true_prob * payout) - stake
            payout = stake * (combined_decimal - 1)
            ev = (combined_true_prob * payout) - ((1 - combined_true_prob) * stake)
            roi = ev / stake
            edge = combined_true_prob - combined_implied_prob

            # Combined American odds
            if combined_decimal >= 2.0:
                combined_american = int(round((combined_decimal - 1) * 100))
            else:
                combined_american = int(round(-100 / (combined_decimal - 1)))

            parlays.append({
                "legs": [
                    {
                        "pick": leg["pick"],
                        "game": leg["game"],
                        "odds": leg["odds"],
                        "decimal_odds": leg["decimal_odds"],
                        "true_prob": leg["true_prob"],
                        "implied_prob": leg["implied_prob"],
                        "edge": leg["edge"],
                        "bet_type": leg["bet_type"],
                        "book": leg["book"],
                    }
                    for leg in combo
                ],
                "n_legs": n_legs,
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

    # Sort by EV descending
    parlays.sort(key=lambda p: p["ev"], reverse=True)

    # Return top 10 parlays
    return parlays[:10]


def kelly_criterion(true_prob: float, decimal_odds: float, fraction: float = 0.25) -> float:
    """
    Kelly criterion for optimal bet sizing.
    Returns fraction of bankroll to bet.
    Uses fractional Kelly (default 1/4) for safety.

    f* = (bp - q) / b
    where b = decimal_odds - 1, p = true_prob, q = 1 - p
    """
    b = decimal_odds - 1
    p = true_prob
    q = 1 - p

    full_kelly = (b * p - q) / b
    if full_kelly <= 0:
        return 0.0

    return full_kelly * fraction
