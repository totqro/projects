#!/usr/bin/env python3
"""
Comprehensive Model Configuration Optimizer
=============================================
Tests a wide range of variable combinations and parameter magnitudes
against real bet results to find the highest-performing configurations.

Uses 144 resolved bets (March 1 - April 5, 2026) as the test dataset.

Dimensions tested:
1. Book filter (soft-only vs all vs specific exclusions)
2. Bet type filter (ML only, Totals only, both)
3. Min edge threshold (2%-10% in 0.5% steps)
4. Min confidence threshold (0.30-0.80)
5. Edge cap (remove suspiciously high edges)
6. Under bet penalty (exclude unders, require higher edge)
7. Sharp book exclusion patterns
8. Bet grade filters (A-only, A+B+, etc.)
9. Kelly criterion fraction (sizing impact)
10. Combined multi-factor configurations
"""

import json
import itertools
from pathlib import Path
from collections import defaultdict
from datetime import datetime

# ─── Sharp/Soft Book Definitions ───────────────────────────────────────────
SHARP_BOOKS = {"fanduel", "betparx", "lowvig", "fliff", "pinnacle", "betcris"}
SOFT_BOOKS = {
    "espnbet", "betmgm", "bovada", "ballybet", "draftkings",
    "betrivers", "pointsbet", "thescore", "betway", "bet365",
    "williamhill_us", "unibet_us", "superbook", "twinspires",
    "wynnbet", "hardrockbet",
}
# Semi-sharp: books that aren't in either list (betus, betonlineag, mybookieag, betanysports)
SEMI_SHARP = {"betus", "betonlineag", "mybookieag", "betanysports"}


def load_bet_results():
    """Load all resolved bet results."""
    path = Path(__file__).parent / "data" / "bet_results.json"
    with open(path) as f:
        data = json.load(f)
    return data.get("results", {})


def evaluate_configuration(bets, config):
    """
    Apply a configuration filter to bets and calculate performance.

    Config keys:
    - book_filter: "soft", "all", "soft+semi", "exclude_worst"
    - bet_type: "all", "Moneyline", "Total"
    - min_edge: float (minimum edge to take bet)
    - max_edge: float (cap suspicious edges)
    - min_confidence: float
    - exclude_unders: bool
    - under_min_edge: float (higher edge requirement for unders)
    - min_odds: int (minimum american odds, e.g. -200)
    - max_odds: int (maximum american odds, e.g. +300)
    - kelly_fraction: float (for sizing)

    Returns dict with performance metrics or None if too few bets.
    """
    book_filter = config.get("book_filter", "soft")
    bet_type = config.get("bet_type", "all")
    min_edge = config.get("min_edge", 0.02)
    max_edge = config.get("max_edge", 1.0)
    min_confidence = config.get("min_confidence", 0.30)
    exclude_unders = config.get("exclude_unders", False)
    under_min_edge = config.get("under_min_edge", None)
    min_odds = config.get("min_odds", -500)
    max_odds = config.get("max_odds", 500)
    kelly_fraction = config.get("kelly_fraction", 0.25)

    filtered = []

    for bet_id, result in bets.items():
        bet = result["bet"]
        outcome = result["result"]
        if outcome == "push":
            continue

        book = bet.get("book", "").lower()
        b_type = bet.get("bet_type", "")
        edge = bet.get("edge", 0)
        confidence = bet.get("confidence", 0)
        odds = bet.get("american_odds", bet.get("odds", -110))
        pick = bet.get("pick", "")

        # Book filter
        if book_filter == "soft":
            if book in SHARP_BOOKS or book in SEMI_SHARP:
                continue
        elif book_filter == "soft+semi":
            if book in SHARP_BOOKS:
                continue
        elif book_filter == "exclude_worst":
            # Exclude only the worst-performing sharp books
            if book in {"fliff", "betparx", "lowvig"}:
                continue
        # "all" = no filter

        # Bet type filter
        if bet_type != "all" and b_type != bet_type:
            continue

        # Edge filter
        if edge < min_edge or edge > max_edge:
            continue

        # Confidence filter
        if confidence < min_confidence:
            continue

        # Under filter
        if exclude_unders and "Under" in pick:
            continue

        # Under higher edge requirement
        if under_min_edge and "Under" in pick and edge < under_min_edge:
            continue

        # Odds range filter
        if odds < min_odds or odds > max_odds:
            continue

        # Calculate Kelly stake
        decimal_odds = bet.get("decimal_odds", 1.91)
        true_prob = bet.get("true_prob", 0.5)
        b = decimal_odds - 1
        p = true_prob
        q = 1 - p
        full_kelly = (b * p - q) / b if b > 0 else 0
        kelly_stake = max(0, full_kelly * kelly_fraction)

        won = outcome == "won"
        profit = result.get("profit", 0)
        stake = bet.get("stake", 0.5)

        filtered.append({
            "bet_id": bet_id,
            "won": won,
            "profit": profit,
            "stake": stake,
            "edge": edge,
            "confidence": confidence,
            "bet_type": b_type,
            "book": book,
            "odds": odds,
            "pick": pick,
            "kelly_stake": kelly_stake,
            "true_prob": true_prob,
        })

    if len(filtered) < 5:
        return None

    # Calculate metrics
    total_bets = len(filtered)
    wins = sum(1 for b in filtered if b["won"])
    losses = total_bets - wins
    win_rate = wins / total_bets

    total_staked = sum(b["stake"] for b in filtered)
    total_profit = sum(b["profit"] for b in filtered)
    roi = (total_profit / total_staked * 100) if total_staked > 0 else 0

    avg_edge = sum(b["edge"] for b in filtered) / total_bets
    avg_confidence = sum(b["confidence"] for b in filtered) / total_bets
    avg_odds = sum(b["odds"] for b in filtered) / total_bets

    # Kelly-weighted ROI (using Kelly sizing instead of flat)
    kelly_profit = 0
    kelly_staked = 0
    for b in filtered:
        ks = max(b["kelly_stake"], 0.01)  # min 1% of bankroll
        kelly_staked += ks
        if b["won"]:
            kelly_profit += ks * (b.get("true_prob", 0.5) / (1 - b.get("true_prob", 0.5)))
        else:
            kelly_profit -= ks
    kelly_roi = (kelly_profit / kelly_staked * 100) if kelly_staked > 0 else 0

    # Profit by bet type
    type_stats = defaultdict(lambda: {"won": 0, "total": 0, "profit": 0, "staked": 0})
    for b in filtered:
        t = b["bet_type"]
        type_stats[t]["total"] += 1
        type_stats[t]["staked"] += b["stake"]
        type_stats[t]["profit"] += b["profit"]
        if b["won"]:
            type_stats[t]["won"] += 1

    # Book stats
    book_stats = defaultdict(lambda: {"won": 0, "total": 0, "profit": 0})
    for b in filtered:
        bk = b["book"]
        book_stats[bk]["total"] += 1
        book_stats[bk]["profit"] += b["profit"]
        if b["won"]:
            book_stats[bk]["won"] += 1

    # Streak analysis (longest win/loss streak)
    max_win_streak = 0
    max_loss_streak = 0
    current_streak = 0
    for b in filtered:
        if b["won"]:
            current_streak = max(1, current_streak + 1) if current_streak > 0 else 1
            max_win_streak = max(max_win_streak, current_streak)
        else:
            current_streak = min(-1, current_streak - 1) if current_streak < 0 else -1
            max_loss_streak = max(max_loss_streak, abs(current_streak))

    # Sharpe-like ratio (profit consistency)
    if total_bets > 1:
        profits = [b["profit"] for b in filtered]
        mean_profit = sum(profits) / len(profits)
        variance = sum((p - mean_profit) ** 2 for p in profits) / (len(profits) - 1)
        std_profit = variance ** 0.5
        sharpe = (mean_profit / std_profit) if std_profit > 0 else 0
    else:
        sharpe = 0

    return {
        "total_bets": total_bets,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "total_staked": total_staked,
        "total_profit": total_profit,
        "roi": roi,
        "avg_edge": avg_edge,
        "avg_confidence": avg_confidence,
        "avg_odds": avg_odds,
        "kelly_roi": kelly_roi,
        "sharpe": sharpe,
        "max_win_streak": max_win_streak,
        "max_loss_streak": max_loss_streak,
        "type_stats": dict(type_stats),
        "book_stats": dict(book_stats),
    }


def generate_configurations():
    """Generate all configuration combinations to test."""
    configs = []

    # ═══════════════════════════════════════════════════════════════════
    # PHASE 1: Single-variable sweeps (isolate each variable's impact)
    # ═══════════════════════════════════════════════════════════════════

    # 1A. Book filter sweep
    for bf in ["soft", "soft+semi", "exclude_worst", "all"]:
        configs.append({
            "name": f"book={bf}",
            "book_filter": bf,
            "bet_type": "all",
            "min_edge": 0.02,
            "min_confidence": 0.30,
        })

    # 1B. Bet type sweep
    for bt in ["all", "Moneyline", "Total"]:
        configs.append({
            "name": f"type={bt}",
            "book_filter": "all",
            "bet_type": bt,
            "min_edge": 0.02,
            "min_confidence": 0.30,
        })

    # 1C. Min edge sweep (fine-grained)
    for me in [0.02, 0.025, 0.03, 0.035, 0.04, 0.045, 0.05, 0.06, 0.07, 0.08, 0.10]:
        configs.append({
            "name": f"edge>={me:.1%}",
            "book_filter": "all",
            "bet_type": "all",
            "min_edge": me,
            "min_confidence": 0.30,
        })

    # 1D. Max edge sweep (remove suspiciously high edges)
    for mx in [0.08, 0.10, 0.12, 0.15, 0.20, 1.0]:
        configs.append({
            "name": f"edge<={mx:.0%}",
            "book_filter": "all",
            "bet_type": "all",
            "min_edge": 0.02,
            "max_edge": mx,
            "min_confidence": 0.30,
        })

    # 1E. Confidence sweep
    for mc in [0.30, 0.40, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]:
        configs.append({
            "name": f"conf>={mc:.0%}",
            "book_filter": "all",
            "bet_type": "all",
            "min_edge": 0.02,
            "min_confidence": mc,
        })

    # 1F. Under bet handling
    configs.append({
        "name": "no_unders",
        "book_filter": "all",
        "bet_type": "all",
        "min_edge": 0.02,
        "min_confidence": 0.30,
        "exclude_unders": True,
    })
    for ue in [0.04, 0.05, 0.06, 0.08]:
        configs.append({
            "name": f"under_edge>={ue:.0%}",
            "book_filter": "all",
            "bet_type": "all",
            "min_edge": 0.02,
            "min_confidence": 0.30,
            "under_min_edge": ue,
        })

    # 1G. Odds range filters
    for min_o in [-300, -200, -150]:
        configs.append({
            "name": f"odds>={min_o}",
            "book_filter": "all",
            "bet_type": "all",
            "min_edge": 0.02,
            "min_confidence": 0.30,
            "min_odds": min_o,
        })
    for max_o in [150, 200, 250, 300]:
        configs.append({
            "name": f"odds<={max_o:+d}",
            "book_filter": "all",
            "bet_type": "all",
            "min_edge": 0.02,
            "min_confidence": 0.30,
            "max_odds": max_o,
        })

    # ═══════════════════════════════════════════════════════════════════
    # PHASE 2: Two-variable combinations (find synergies)
    # ═══════════════════════════════════════════════════════════════════

    # Book filter x Edge threshold
    for bf in ["soft", "soft+semi", "exclude_worst"]:
        for me in [0.03, 0.04, 0.05, 0.06, 0.07, 0.08]:
            configs.append({
                "name": f"book={bf}|edge>={me:.0%}",
                "book_filter": bf,
                "bet_type": "all",
                "min_edge": me,
                "min_confidence": 0.30,
            })

    # Book filter x Bet type
    for bf in ["soft", "soft+semi", "exclude_worst"]:
        for bt in ["Moneyline", "Total"]:
            configs.append({
                "name": f"book={bf}|type={bt}",
                "book_filter": bf,
                "bet_type": bt,
                "min_edge": 0.02,
                "min_confidence": 0.30,
            })

    # Edge x Confidence
    for me in [0.03, 0.04, 0.05, 0.06]:
        for mc in [0.50, 0.60, 0.70]:
            configs.append({
                "name": f"edge>={me:.0%}|conf>={mc:.0%}",
                "book_filter": "all",
                "bet_type": "all",
                "min_edge": me,
                "min_confidence": mc,
            })

    # Edge x Bet type
    for me in [0.03, 0.04, 0.05, 0.06]:
        for bt in ["Moneyline", "Total"]:
            configs.append({
                "name": f"edge>={me:.0%}|type={bt}",
                "book_filter": "all",
                "bet_type": bt,
                "min_edge": me,
                "min_confidence": 0.30,
            })

    # Edge band analysis (is the model best in a specific edge range?)
    edge_bands = [
        (0.02, 0.04), (0.04, 0.06), (0.06, 0.08), (0.08, 0.12),
        (0.03, 0.06), (0.04, 0.08), (0.05, 0.10), (0.03, 0.08),
    ]
    for lo, hi in edge_bands:
        configs.append({
            "name": f"edge_band={lo:.0%}-{hi:.0%}",
            "book_filter": "all",
            "bet_type": "all",
            "min_edge": lo,
            "max_edge": hi,
            "min_confidence": 0.30,
        })

    # ═══════════════════════════════════════════════════════════════════
    # PHASE 3: Multi-variable "strategy" configurations
    # ═══════════════════════════════════════════════════════════════════

    # Conservative strategy
    configs.append({
        "name": "CONSERVATIVE",
        "book_filter": "soft",
        "bet_type": "all",
        "min_edge": 0.05,
        "min_confidence": 0.60,
        "exclude_unders": True,
    })

    # Aggressive strategy
    configs.append({
        "name": "AGGRESSIVE",
        "book_filter": "all",
        "bet_type": "all",
        "min_edge": 0.02,
        "min_confidence": 0.30,
    })

    # ML-only sharp filter
    configs.append({
        "name": "ML_SOFT_HIGH_EDGE",
        "book_filter": "soft",
        "bet_type": "Moneyline",
        "min_edge": 0.04,
        "min_confidence": 0.50,
    })

    # Totals specialist
    configs.append({
        "name": "TOTALS_SPECIALIST",
        "book_filter": "soft+semi",
        "bet_type": "Total",
        "min_edge": 0.03,
        "min_confidence": 0.50,
        "exclude_unders": True,
    })

    # High-confidence plays
    configs.append({
        "name": "HIGH_CONF_HIGH_EDGE",
        "book_filter": "exclude_worst",
        "bet_type": "all",
        "min_edge": 0.05,
        "min_confidence": 0.70,
    })

    # Value hunter (big edge, any book)
    configs.append({
        "name": "VALUE_HUNTER",
        "book_filter": "all",
        "bet_type": "all",
        "min_edge": 0.07,
        "min_confidence": 0.30,
    })

    # Balanced approach
    configs.append({
        "name": "BALANCED",
        "book_filter": "exclude_worst",
        "bet_type": "all",
        "min_edge": 0.04,
        "min_confidence": 0.50,
        "under_min_edge": 0.06,
    })

    # Soft books + ML + moderate edge
    configs.append({
        "name": "SOFT_ML_MODERATE",
        "book_filter": "soft",
        "bet_type": "Moneyline",
        "min_edge": 0.03,
        "min_confidence": 0.60,
    })

    # No heavy favorites
    configs.append({
        "name": "NO_HEAVY_FAVS",
        "book_filter": "exclude_worst",
        "bet_type": "all",
        "min_edge": 0.04,
        "min_confidence": 0.50,
        "min_odds": -200,
    })

    # Underdog specialist
    configs.append({
        "name": "UNDERDOG_SPEC",
        "book_filter": "all",
        "bet_type": "Moneyline",
        "min_edge": 0.04,
        "min_confidence": 0.30,
        "min_odds": 100,
    })

    # Slight favorites
    configs.append({
        "name": "SLIGHT_FAVS",
        "book_filter": "exclude_worst",
        "bet_type": "Moneyline",
        "min_edge": 0.03,
        "min_confidence": 0.50,
        "min_odds": -200,
        "max_odds": -100,
    })

    # Over specialist
    configs.append({
        "name": "OVERS_ONLY",
        "book_filter": "soft+semi",
        "bet_type": "Total",
        "min_edge": 0.03,
        "min_confidence": 0.50,
        "exclude_unders": True,
    })

    # Strict quality gate
    configs.append({
        "name": "STRICT_QUALITY",
        "book_filter": "soft",
        "bet_type": "all",
        "min_edge": 0.06,
        "min_confidence": 0.65,
        "max_edge": 0.15,
        "under_min_edge": 0.08,
    })

    # Medium edge band on soft books
    configs.append({
        "name": "SOFT_MED_EDGE",
        "book_filter": "soft",
        "bet_type": "all",
        "min_edge": 0.04,
        "max_edge": 0.10,
        "min_confidence": 0.50,
    })

    # Best books only (based on historical performance)
    configs.append({
        "name": "BEST_BOOKS_ONLY",
        "book_filter": "soft",  # will be further filtered below
        "bet_type": "all",
        "min_edge": 0.03,
        "min_confidence": 0.50,
    })

    return configs


def run_optimization():
    """Run all configurations and produce ranked results."""
    print("=" * 90)
    print("  NHL MODEL CONFIGURATION OPTIMIZER")
    print("  Testing variable combinations against 144 real bet results")
    print("=" * 90)
    print()

    # Load data
    bets = load_bet_results()
    total_bets = len(bets)
    wins = sum(1 for r in bets.values() if r["result"] == "won")
    losses = sum(1 for r in bets.values() if r["result"] == "lost")
    total_profit = sum(r.get("profit", 0) for r in bets.values())
    total_staked = sum(r["bet"].get("stake", 0.5) for r in bets.values())

    print(f"  Dataset: {total_bets} resolved bets")
    print(f"  Period: March 1 - April 5, 2026")
    print(f"  Baseline: {wins}W-{losses}L ({wins/total_bets:.1%} WR) | ${total_profit:+.2f} profit | {total_profit/total_staked*100:+.1f}% ROI")
    print()

    # Generate and test configurations
    configs = generate_configurations()
    print(f"  Testing {len(configs)} configurations...")
    print()

    results = []
    for config in configs:
        perf = evaluate_configuration(bets, config)
        if perf:
            results.append({
                "name": config.get("name", "unnamed"),
                "config": config,
                **perf,
            })

    # Sort by ROI
    results.sort(key=lambda x: x["roi"], reverse=True)

    # ═══════════════════════════════════════════════════════════════════
    # REPORT: Top performing configurations
    # ═══════════════════════════════════════════════════════════════════
    print("=" * 90)
    print("  TOP 40 CONFIGURATIONS BY ROI")
    print("=" * 90)
    print()
    print(f"  {'Rank':<5} {'Configuration':<35} {'Bets':>5} {'W-L':>8} {'WR':>7} {'ROI':>8} {'Profit':>9} {'AvgEdge':>8} {'Sharpe':>7}")
    print("  " + "-" * 88)

    for i, r in enumerate(results[:40], 1):
        wl = f"{r['wins']}-{r['losses']}"
        print(f"  {i:<5} {r['name']:<35} {r['total_bets']:>5} {wl:>8} {r['win_rate']:>6.1%} {r['roi']:>+7.1f}% ${r['total_profit']:>+7.2f} {r['avg_edge']:>7.1%} {r['sharpe']:>+6.2f}")

    # ═══════════════════════════════════════════════════════════════════
    # REPORT: Bottom performing configurations (what to avoid)
    # ═══════════════════════════════════════════════════════════════════
    print()
    print("=" * 90)
    print("  BOTTOM 15 CONFIGURATIONS (WHAT TO AVOID)")
    print("=" * 90)
    print()
    print(f"  {'Rank':<5} {'Configuration':<35} {'Bets':>5} {'W-L':>8} {'WR':>7} {'ROI':>8} {'Profit':>9}")
    print("  " + "-" * 78)

    bottom = sorted(results, key=lambda x: x["roi"])[:15]
    for i, r in enumerate(bottom, 1):
        wl = f"{r['wins']}-{r['losses']}"
        print(f"  {i:<5} {r['name']:<35} {r['total_bets']:>5} {wl:>8} {r['win_rate']:>6.1%} {r['roi']:>+7.1f}% ${r['total_profit']:>+7.2f}")

    # ═══════════════════════════════════════════════════════════════════
    # ANALYSIS: Single-variable impact
    # ═══════════════════════════════════════════════════════════════════
    print()
    print("=" * 90)
    print("  SINGLE-VARIABLE IMPACT ANALYSIS")
    print("=" * 90)

    # Book filter impact
    print("\n  Book Filter Impact:")
    print("  " + "-" * 60)
    for r in results:
        if r["name"].startswith("book=") and "|" not in r["name"]:
            print(f"    {r['name']:<25} {r['total_bets']:>4} bets | {r['win_rate']:.1%} WR | {r['roi']:+.1f}% ROI")

    # Bet type impact
    print("\n  Bet Type Impact:")
    print("  " + "-" * 60)
    for r in results:
        if r["name"].startswith("type="):
            print(f"    {r['name']:<25} {r['total_bets']:>4} bets | {r['win_rate']:.1%} WR | {r['roi']:+.1f}% ROI")

    # Edge threshold impact
    print("\n  Min Edge Threshold Impact:")
    print("  " + "-" * 60)
    edge_results = [r for r in results if r["name"].startswith("edge>=") and "|" not in r["name"]]
    edge_results.sort(key=lambda x: x["config"]["min_edge"])
    for r in edge_results:
        bar = "█" * max(0, int((r["roi"] + 30) / 2))  # visual bar
        print(f"    {r['name']:<25} {r['total_bets']:>4} bets | {r['win_rate']:.1%} WR | {r['roi']:+.1f}% ROI {bar}")

    # Confidence threshold impact
    print("\n  Min Confidence Impact:")
    print("  " + "-" * 60)
    conf_results = [r for r in results if r["name"].startswith("conf>=")]
    conf_results.sort(key=lambda x: x["config"]["min_confidence"])
    for r in conf_results:
        print(f"    {r['name']:<25} {r['total_bets']:>4} bets | {r['win_rate']:.1%} WR | {r['roi']:+.1f}% ROI")

    # Max edge impact
    print("\n  Max Edge Cap Impact:")
    print("  " + "-" * 60)
    maxe_results = [r for r in results if r["name"].startswith("edge<=")]
    maxe_results.sort(key=lambda x: x["config"].get("max_edge", 1.0))
    for r in maxe_results:
        print(f"    {r['name']:<25} {r['total_bets']:>4} bets | {r['win_rate']:.1%} WR | {r['roi']:+.1f}% ROI")

    # Under handling
    print("\n  Under Bet Handling:")
    print("  " + "-" * 60)
    under_results = [r for r in results if "under" in r["name"].lower() or "no_under" in r["name"].lower()]
    for r in under_results:
        print(f"    {r['name']:<25} {r['total_bets']:>4} bets | {r['win_rate']:.1%} WR | {r['roi']:+.1f}% ROI")

    # Odds range impact
    print("\n  Odds Range Impact:")
    print("  " + "-" * 60)
    odds_results = [r for r in results if r["name"].startswith("odds")]
    for r in odds_results:
        print(f"    {r['name']:<25} {r['total_bets']:>4} bets | {r['win_rate']:.1%} WR | {r['roi']:+.1f}% ROI")

    # Edge band analysis
    print("\n  Edge Band Analysis:")
    print("  " + "-" * 60)
    band_results = [r for r in results if r["name"].startswith("edge_band")]
    band_results.sort(key=lambda x: x["config"]["min_edge"])
    for r in band_results:
        print(f"    {r['name']:<25} {r['total_bets']:>4} bets | {r['win_rate']:.1%} WR | {r['roi']:+.1f}% ROI")

    # ═══════════════════════════════════════════════════════════════════
    # ANALYSIS: Book-level performance (across all bets)
    # ═══════════════════════════════════════════════════════════════════
    print()
    print("=" * 90)
    print("  BOOK-LEVEL PERFORMANCE (ALL BETS)")
    print("=" * 90)
    print()

    baseline = evaluate_configuration(bets, {
        "book_filter": "all", "bet_type": "all",
        "min_edge": 0.0, "min_confidence": 0.0,
    })
    if baseline and baseline.get("book_stats"):
        book_perf = []
        for book, stats in baseline["book_stats"].items():
            wr = stats["won"] / stats["total"] if stats["total"] > 0 else 0
            book_perf.append((book, stats["total"], stats["won"], wr, stats["profit"]))
        book_perf.sort(key=lambda x: x[4] / max(x[1] * 0.5, 0.01), reverse=True)  # Sort by ROI

        print(f"  {'Book':<20} {'Bets':>5} {'Won':>5} {'WR':>7} {'Profit':>9} {'ROI':>8}")
        print("  " + "-" * 58)
        for book, total, won, wr, profit in book_perf:
            staked = total * 0.5  # Approximate
            roi = (profit / staked * 100) if staked > 0 else 0
            indicator = "+++" if roi > 20 else ("++" if roi > 0 else ("--" if roi < -20 else "-"))
            print(f"  {book:<20} {total:>5} {won:>5} {wr:>6.1%} ${profit:>+7.2f} {roi:>+7.1f}% {indicator}")

    # ═══════════════════════════════════════════════════════════════════
    # ANALYSIS: Bet type performance detail
    # ═══════════════════════════════════════════════════════════════════
    print()
    print("=" * 90)
    print("  BET TYPE PERFORMANCE DETAIL")
    print("=" * 90)
    print()

    if baseline and baseline.get("type_stats"):
        for bt, stats in baseline["type_stats"].items():
            wr = stats["won"] / stats["total"] if stats["total"] > 0 else 0
            roi = (stats["profit"] / stats["staked"] * 100) if stats["staked"] > 0 else 0
            print(f"  {bt}: {stats['total']} bets | {stats['won']}W-{stats['total']-stats['won']}L | {wr:.1%} WR | {roi:+.1f}% ROI | ${stats['profit']:+.2f}")

    # ═══════════════════════════════════════════════════════════════════
    # PATTERN RECOGNITION
    # ═══════════════════════════════════════════════════════════════════
    print()
    print("=" * 90)
    print("  PATTERN RECOGNITION: WHAT WORKS & WHAT DOESN'T")
    print("=" * 90)
    print()

    # Find profitable configs
    profitable = [r for r in results if r["roi"] > 0 and r["total_bets"] >= 8]
    unprofitable = [r for r in results if r["roi"] < -10 and r["total_bets"] >= 8]

    if profitable:
        print("  PATTERNS IN PROFITABLE CONFIGURATIONS:")
        print("  " + "-" * 60)

        # Count which settings appear in profitable configs
        book_counts = defaultdict(int)
        type_counts = defaultdict(int)
        edge_ranges = []
        conf_ranges = []

        for r in profitable:
            c = r["config"]
            book_counts[c.get("book_filter", "all")] += 1
            type_counts[c.get("bet_type", "all")] += 1
            edge_ranges.append(c.get("min_edge", 0.02))
            conf_ranges.append(c.get("min_confidence", 0.30))

        total_p = len(profitable)
        print(f"\n    Book filter distribution ({total_p} profitable configs):")
        for bf, count in sorted(book_counts.items(), key=lambda x: -x[1]):
            print(f"      {bf}: {count} ({count/total_p:.0%})")

        print(f"\n    Bet type distribution:")
        for bt, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            print(f"      {bt}: {count} ({count/total_p:.0%})")

        print(f"\n    Min edge range: {min(edge_ranges):.1%} - {max(edge_ranges):.1%} (median: {sorted(edge_ranges)[len(edge_ranges)//2]:.1%})")
        print(f"    Min confidence range: {min(conf_ranges):.0%} - {max(conf_ranges):.0%} (median: {sorted(conf_ranges)[len(conf_ranges)//2]:.0%})")

    if unprofitable:
        print("\n  PATTERNS IN WORST-PERFORMING CONFIGURATIONS:")
        print("  " + "-" * 60)

        book_counts = defaultdict(int)
        for r in unprofitable:
            book_counts[r["config"].get("book_filter", "all")] += 1
        for bf, count in sorted(book_counts.items(), key=lambda x: -x[1]):
            print(f"    {bf}: {count} configs")

    # ═══════════════════════════════════════════════════════════════════
    # FINAL RECOMMENDATION
    # ═══════════════════════════════════════════════════════════════════
    print()
    print("=" * 90)
    print("  FINAL RECOMMENDATION & DECISION GATE")
    print("=" * 90)
    print()

    # Find best config with sufficient sample size
    viable = [r for r in results if r["total_bets"] >= 10]
    viable.sort(key=lambda x: x["roi"], reverse=True)

    if viable and viable[0]["roi"] > 0:
        best = viable[0]
        print(f"  BEST VIABLE CONFIGURATION: {best['name']}")
        print(f"  " + "-" * 60)
        print(f"    Bets:       {best['total_bets']}")
        print(f"    Record:     {best['wins']}W-{best['losses']}L ({best['win_rate']:.1%})")
        print(f"    ROI:        {best['roi']:+.1f}%")
        print(f"    Profit:     ${best['total_profit']:+.2f}")
        print(f"    Avg Edge:   {best['avg_edge']:.1%}")
        print(f"    Sharpe:     {best['sharpe']:+.3f}")
        print()
        print(f"  Settings:")
        for k, v in best["config"].items():
            if k != "name":
                print(f"    {k}: {v}")
        print()

        # Top 5 viable
        print("  TOP 5 VIABLE CONFIGURATIONS (10+ bets):")
        print("  " + "-" * 80)
        for i, r in enumerate(viable[:5], 1):
            print(f"    {i}. {r['name']:<30} {r['total_bets']:>3} bets | {r['win_rate']:.1%} WR | {r['roi']:+.1f}% ROI | ${r['total_profit']:+.2f}")
        print()

        # Decision gate
        positive_count = sum(1 for r in viable if r["roi"] > 0)
        consistent = sum(1 for r in viable[:10] if r["roi"] > 0)

        print(f"  DECISION GATE:")
        print(f"    Configs with positive ROI (10+ bets): {positive_count}/{len(viable)}")
        print(f"    Top 10 configs with positive ROI: {consistent}/10")
        print()

        if positive_count >= 5 and consistent >= 3:
            print("  >>> DECISION: GO <<<")
            print("  Multiple configurations show consistent positive ROI.")
            print("  Implement the top configuration and monitor for 2 weeks.")
        elif positive_count >= 2:
            print("  >>> DECISION: ITERATE <<<")
            print("  Some positive configurations exist but results are not consistent.")
            print("  Focus on the top settings and collect more data before committing.")
        else:
            print("  >>> DECISION: STOP <<<")
            print("  No configuration shows reliable edge over sportsbook lines.")
            print("  Fundamental model improvements needed before deployment.")
    else:
        print("  >>> DECISION: STOP <<<")
        print("  No configuration with 10+ bets shows positive ROI.")
        print("  The model does not currently have a detectable edge.")
        print()
        print("  RECOMMENDED NEXT STEPS:")
        print("  1. Investigate calibration: model predicts ~50% but wins ~43%")
        print("  2. Check if sharp book lines have moved by bet placement time")
        print("  3. Consider CLV tracking to separate model quality from variance")
        print("  4. Review if 144 bets is sufficient sample (likely need 500+)")

    # ═══════════════════════════════════════════════════════════════════
    # Save results to file
    # ═══════════════════════════════════════════════════════════════════
    output_path = Path(__file__).parent / "data" / "optimization_results.json"
    save_data = {
        "run_date": datetime.now().isoformat(),
        "dataset_size": total_bets,
        "configurations_tested": len(configs),
        "configurations_with_results": len(results),
        "top_20": [
            {
                "rank": i + 1,
                "name": r["name"],
                "config": r["config"],
                "total_bets": r["total_bets"],
                "wins": r["wins"],
                "losses": r["losses"],
                "win_rate": r["win_rate"],
                "roi": r["roi"],
                "total_profit": r["total_profit"],
                "avg_edge": r["avg_edge"],
                "sharpe": r["sharpe"],
            }
            for i, r in enumerate(results[:20])
        ],
        "all_results_summary": [
            {
                "name": r["name"],
                "bets": r["total_bets"],
                "win_rate": round(r["win_rate"], 3),
                "roi": round(r["roi"], 1),
                "profit": round(r["total_profit"], 2),
            }
            for r in results
        ],
    }
    output_path.write_text(json.dumps(save_data, indent=2))
    print(f"\n  Results saved to: {output_path}")
    print("=" * 90)

    return results


if __name__ == "__main__":
    results = run_optimization()
