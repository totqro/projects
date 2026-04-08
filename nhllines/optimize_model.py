#!/usr/bin/env python3
"""
Brute-force optimizer: test every combination of filtering rules against
historical bet results to find the most profitable configuration.

Parameters varied:
  - min_edge: minimum edge threshold (3% to 10%)
  - bet_types: which bet types to allow (ML only, Totals only, both, overs only)
  - min_confidence: minimum confidence to take a bet
  - underdog_filter: whether to skip underdogs or require higher edge
  - model_weight: model vs market blend (tested retroactively via true_prob scaling)
  - book_filter: which books to allow
"""

import json
from itertools import product
from pathlib import Path

from src.data.odds_fetcher import american_to_decimal


def load_results():
    """Load all bet results."""
    path = Path("data/bet_results.json")
    data = json.loads(path.read_text())
    return list(data["results"].values())


def simulate(results, config):
    """
    Simulate profit/loss for a set of results under a given config.
    Returns dict with stats.
    """
    min_edge = config["min_edge"]
    min_confidence = config["min_confidence"]
    allowed_types = config["allowed_types"]  # set of bet types
    underdog_min_edge = config["underdog_min_edge"]  # extra edge for dogs
    favorite_only = config.get("favorite_only", False)
    max_implied_prob = config.get("max_implied_prob", 1.0)  # skip heavy favorites
    min_true_prob = config.get("min_true_prob", 0.0)
    allowed_picks = config.get("allowed_picks", None)  # "over", "under", None=both
    book_filter = config.get("book_filter", None)  # set of allowed books or None

    won = 0
    lost = 0
    profit = 0.0
    staked = 0.0
    bets_taken = []

    for r in results:
        bet = r["bet"]
        result = r["result"]
        if result == "push":
            continue

        bt = bet["bet_type"]
        edge = bet.get("edge", 0)
        conf = bet.get("confidence", 0.5)
        odds = bet.get("odds", 0)
        true_prob = bet.get("true_prob", 0.5)
        implied = bet.get("implied_prob", 0.5)
        pick = bet.get("pick", "")
        book = bet.get("book", "").lower()

        # --- FILTERS ---
        if bt not in allowed_types:
            continue

        if edge < min_edge:
            continue

        if conf < min_confidence:
            continue

        if true_prob < min_true_prob:
            continue

        if implied > max_implied_prob:
            continue

        # Book filter
        if book_filter and book not in book_filter:
            continue

        # Underdog filter (positive odds = underdog)
        if bt == "Moneyline":
            if favorite_only and odds > 0:
                continue
            if odds > 0 and edge < underdog_min_edge:
                continue

        # Over/Under filter
        if bt == "Total" and allowed_picks:
            if allowed_picks == "over" and "Under" in pick:
                continue
            if allowed_picks == "under" and "Over" in pick:
                continue

        # --- CALCULATE P&L ---
        stake = bet.get("stake", 0.5)
        staked += stake

        if result == "won":
            decimal_odds = american_to_decimal(odds)
            profit += stake * (decimal_odds - 1)
            won += 1
        else:
            profit -= stake
            lost += 1

        bets_taken.append(r)

    total = won + lost
    return {
        "won": won,
        "lost": lost,
        "total": total,
        "win_rate": won / total if total else 0,
        "profit": profit,
        "staked": staked,
        "roi": profit / staked if staked > 0 else 0,
        "config": config,
    }


def main():
    results = load_results()
    print(f"Loaded {len(results)} historical results\n")

    # Current baseline
    baseline = simulate(results, {
        "min_edge": 0.04,
        "min_confidence": 0.50,
        "allowed_types": {"Moneyline", "Total"},
        "underdog_min_edge": 0.04,
    })
    print(f"CURRENT BASELINE:")
    print(f"  {baseline['won']}W-{baseline['lost']}L ({baseline['win_rate']:.1%}) "
          f"| Profit: ${baseline['profit']:+.2f} | ROI: {baseline['roi']:+.1%}")
    print()

    # --- PARAMETER GRID ---
    min_edges = [0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10]
    min_confidences = [0.40, 0.50, 0.60, 0.65, 0.70, 0.75]
    underdog_min_edges = [0.04, 0.06, 0.08, 0.10, 0.12, 0.15, 99.0]  # 99 = no underdogs
    type_combos = [
        {"Moneyline", "Total"},
        {"Moneyline"},
        {"Total"},
    ]
    pick_filters = [None, "over", "under"]
    min_true_probs = [0.0, 0.50, 0.52, 0.55, 0.58, 0.60]

    # Soft books only
    soft_books = {
        "espnbet", "betmgm", "bovada", "ballybet",
        "betrivers", "pointsbet", "hardrockbet",
    }

    book_filters = [None, soft_books]  # None = all books

    best_profit = -999
    best_roi = -999
    best_configs = []
    all_results = []

    total_combos = (len(min_edges) * len(min_confidences) *
                    len(underdog_min_edges) * len(type_combos) *
                    len(pick_filters) * len(min_true_probs) * len(book_filters))
    print(f"Testing {total_combos:,} parameter combinations...\n")

    for me, mc, ude, types, pf, mtp, bf in product(
        min_edges, min_confidences, underdog_min_edges,
        type_combos, pick_filters, min_true_probs, book_filters
    ):
        # Skip nonsensical combos
        if pf and "Total" not in types:
            continue  # over/under filter only matters for totals
        if ude < me:
            continue  # underdog edge can't be less than min edge

        config = {
            "min_edge": me,
            "min_confidence": mc,
            "allowed_types": types,
            "underdog_min_edge": ude,
            "allowed_picks": pf,
            "min_true_prob": mtp,
            "book_filter": bf,
        }

        res = simulate(results, config)

        # Need at least 10 bets for statistical relevance
        if res["total"] < 10:
            continue

        all_results.append(res)

        if res["profit"] > best_profit:
            best_profit = res["profit"]

    # Sort by profit
    all_results.sort(key=lambda x: x["profit"], reverse=True)

    # Top 20 by profit
    print("=" * 90)
    print("  TOP 20 CONFIGURATIONS BY PROFIT")
    print("=" * 90)
    for i, r in enumerate(all_results[:20]):
        c = r["config"]
        types_str = "+".join(sorted(c["allowed_types"]))
        dog_str = f"dog≥{c['underdog_min_edge']:.0%}" if c["underdog_min_edge"] < 90 else "no dogs"
        pick_str = f" {c['allowed_picks']}-only" if c["allowed_picks"] else ""
        prob_str = f" prob≥{c['min_true_prob']:.0%}" if c["min_true_prob"] > 0 else ""
        book_str = " soft-only" if c["book_filter"] else ""
        print(f"  #{i+1:2d}: {r['won']}W-{r['lost']}L ({r['win_rate']:.1%}) "
              f"P=${r['profit']:+.2f} ROI={r['roi']:+.1%} "
              f"| edge≥{c['min_edge']:.0%} conf≥{c['min_confidence']:.0%} "
              f"{types_str} {dog_str}{pick_str}{prob_str}{book_str}")

    # Also show top by ROI (min 15 bets)
    roi_results = [r for r in all_results if r["total"] >= 15]
    roi_results.sort(key=lambda x: x["roi"], reverse=True)

    print()
    print("=" * 90)
    print("  TOP 20 CONFIGURATIONS BY ROI (min 15 bets)")
    print("=" * 90)
    for i, r in enumerate(roi_results[:20]):
        c = r["config"]
        types_str = "+".join(sorted(c["allowed_types"]))
        dog_str = f"dog≥{c['underdog_min_edge']:.0%}" if c["underdog_min_edge"] < 90 else "no dogs"
        pick_str = f" {c['allowed_picks']}-only" if c["allowed_picks"] else ""
        prob_str = f" prob≥{c['min_true_prob']:.0%}" if c["min_true_prob"] > 0 else ""
        book_str = " soft-only" if c["book_filter"] else ""
        print(f"  #{i+1:2d}: {r['won']}W-{r['lost']}L ({r['win_rate']:.1%}) "
              f"P=${r['profit']:+.2f} ROI={r['roi']:+.1%} "
              f"| edge≥{c['min_edge']:.0%} conf≥{c['min_confidence']:.0%} "
              f"{types_str} {dog_str}{pick_str}{prob_str}{book_str}")

    # Best balanced (profit > 0 AND roi > 10% AND >= 20 bets)
    balanced = [r for r in all_results if r["profit"] > 0 and r["roi"] > 0.10 and r["total"] >= 20]
    balanced.sort(key=lambda x: x["profit"], reverse=True)

    print()
    print("=" * 90)
    print("  BEST BALANCED (profit>0, ROI>10%, ≥20 bets)")
    print("=" * 90)
    for i, r in enumerate(balanced[:10]):
        c = r["config"]
        types_str = "+".join(sorted(c["allowed_types"]))
        dog_str = f"dog≥{c['underdog_min_edge']:.0%}" if c["underdog_min_edge"] < 90 else "no dogs"
        pick_str = f" {c['allowed_picks']}-only" if c["allowed_picks"] else ""
        prob_str = f" prob≥{c['min_true_prob']:.0%}" if c["min_true_prob"] > 0 else ""
        book_str = " soft-only" if c["book_filter"] else ""
        print(f"  #{i+1:2d}: {r['won']}W-{r['lost']}L ({r['win_rate']:.1%}) "
              f"P=${r['profit']:+.2f} ROI={r['roi']:+.1%} "
              f"| edge≥{c['min_edge']:.0%} conf≥{c['min_confidence']:.0%} "
              f"{types_str} {dog_str}{pick_str}{prob_str}{book_str}")

    # Print recommended config
    if all_results:
        best = all_results[0]
        c = best["config"]
        print()
        print("=" * 90)
        print("  RECOMMENDED CONFIGURATION")
        print("=" * 90)
        print(f"  min_edge: {c['min_edge']}")
        print(f"  min_confidence: {c['min_confidence']}")
        print(f"  allowed_types: {c['allowed_types']}")
        print(f"  underdog_min_edge: {c['underdog_min_edge']}")
        print(f"  allowed_picks (totals): {c['allowed_picks']}")
        print(f"  min_true_prob: {c['min_true_prob']}")
        print(f"  book_filter: {'soft books only' if c['book_filter'] else 'all books'}")
        print(f"  Expected: {best['won']}W-{best['lost']}L ({best['win_rate']:.1%}) "
              f"| Profit: ${best['profit']:+.2f} | ROI: {best['roi']:+.1%}")


if __name__ == "__main__":
    main()
