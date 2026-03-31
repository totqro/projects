# Closing Line Value (CLV) Implementation Plan

**Priority:** HIGH  
**Status:** Not Implemented  
**Estimated Effort:** 2-3 hours  
**Expected Impact:** HIGH - This is the north star metric

---

## What is CLV?

**Closing Line Value (CLV)** measures how your bet price compares to the closing line (final odds before game starts).

### Why It Matters

1. **Immediate feedback** - Don't wait for game results
2. **Variance-resistant** - Measures skill, not luck
3. **Industry standard** - How sharp bettors measure edge
4. **Predictive** - Positive CLV = long-term profitability

### Example

```
Your bet:  TOR ML at -150 (60% implied)
Closing:   TOR ML at -180 (64.3% implied)
CLV:       +4.3% (you got better odds)
```

Even if TOR loses, you got +EV. Over time, positive CLV = profit.

---

## Current Gap

**What we track:**
- ✅ Odds at time of analysis
- ✅ Market consensus (no-vig probabilities)
- ✅ Our model's predictions
- ✅ Actual bet outcomes

**What we DON'T track:**
- ❌ Closing line odds
- ❌ CLV for each bet
- ❌ CLV by grade
- ❌ CLV trends over time

---

## Implementation Plan

### Phase 1: Store Analysis-Time Odds (Easy)

**Goal:** Save the odds we used for each bet recommendation

**Files to modify:**
- `analysis_history.py`
- `main.py`

**Changes:**

```python
# In analysis_history.py - save_analysis()
# Already stores bet recommendations, just ensure odds are included

bet_record = {
    "game": bet["game"],
    "pick": bet["pick"],
    "odds": bet["odds"],  # ✅ Already stored
    "stake": bet["stake"],
    "edge": bet["edge"],
    "analysis_time": datetime.now().isoformat(),
    "analysis_odds": {  # NEW: Store full odds context
        "moneyline": best_odds["moneyline"],
        "spread": best_odds["spread"],
        "total": best_odds["total"],
        "market_consensus": market_probs,
    }
}
```

**Status:** Mostly done, just need to ensure full odds context is saved.

---

### Phase 2: Fetch Closing Lines (Medium)

**Goal:** Get final odds before game starts

**Options:**

#### Option A: The Odds API (Recommended)
- Fetch odds 5-10 minutes before game start
- Store as "closing line"
- Cost: 1 API request per game
- **Pro:** Already integrated
- **Con:** Need to time it right

#### Option B: Historical Odds Service
- Use service like OddsPortal or SportsbookReview
- Scrape closing lines after the fact
- **Pro:** More reliable
- **Con:** Need new integration

**Recommended:** Start with Option A (The Odds API)

**Implementation:**

```python
# New file: closing_line_fetcher.py

def fetch_closing_lines(game_date):
    """
    Fetch closing lines for games on a specific date.
    Call this 5-10 minutes before first game starts.
    """
    # Use existing odds_fetcher.py infrastructure
    # Store results in cache/closing_lines_{date}.json
    pass

def get_closing_line_for_bet(bet):
    """
    Get closing line for a specific bet.
    Returns odds and implied probability.
    """
    pass
```

**Timing Strategy:**
- Run closing line fetch 10 minutes before first game
- Store in cache
- Use for CLV calculation later

---

### Phase 3: Calculate CLV (Easy)

**Goal:** Compare our odds to closing line

**Formula:**

```python
def calculate_clv(bet_odds, closing_odds):
    """
    Calculate Closing Line Value.
    
    CLV = closing_implied_prob - bet_implied_prob
    
    Positive CLV = we got better odds than closing
    """
    bet_prob = american_to_implied_prob(bet_odds)
    closing_prob = american_to_implied_prob(closing_odds)
    
    clv = closing_prob - bet_prob
    clv_pct = clv * 100  # Convert to percentage
    
    return clv_pct
```

**Example:**
```
Bet odds:     -150 (60.0% implied)
Closing odds: -180 (64.3% implied)
CLV:          +4.3%
```

**Interpretation:**
- CLV > 0: We got better odds (good!)
- CLV = 0: We matched closing line (neutral)
- CLV < 0: We got worse odds (bad)

---

### Phase 4: Track and Report CLV (Medium)

**Goal:** Add CLV to all performance reports

**Files to modify:**
- `bet_tracker.py`
- `main.py` (display)
- `analysis_history.py` (storage)

**New Metrics:**

```python
# In bet_tracker.py - get_performance_stats()

stats = {
    "total_bets": 35,
    "won": 21,
    "win_rate": 0.60,
    "roi": 0.33,
    
    # NEW: CLV metrics
    "avg_clv": 0.023,  # +2.3% average CLV
    "clv_positive_rate": 0.71,  # 71% of bets had positive CLV
    "clv_by_grade": {
        "A": {"avg_clv": 0.045, "positive_rate": 0.85},
        "B+": {"avg_clv": 0.028, "positive_rate": 0.75},
        "B": {"avg_clv": 0.015, "positive_rate": 0.65},
    }
}
```

**Display:**

```
PERFORMANCE SUMMARY
===================
Total bets: 35 | Won: 21 (60.0%) | ROI: +33.0%

CLOSING LINE VALUE (CLV)
=========================
Average CLV: +2.3% ✅
Positive CLV Rate: 71% (25/35 bets)

By Grade:
  [A  ] CLV: +4.5% | Positive: 85%
  [B+ ] CLV: +2.8% | Positive: 75%
  [B  ] CLV: +1.5% | Positive: 65%
```

---

## Implementation Steps

### Step 1: Enhance Analysis Storage (30 min)

```python
# In main.py - run_analysis()

# When saving bet recommendations
bet_record = {
    **bet,  # Existing bet data
    "analysis_time": datetime.now().isoformat(),
    "odds_at_analysis": {
        "moneyline": best_odds["moneyline"],
        "spread": best_odds["spread"],
        "total": best_odds["total"],
    },
    "market_consensus": market_probs,
}
```

### Step 2: Create Closing Line Fetcher (1 hour)

```python
# New file: closing_line_fetcher.py

import json
from pathlib import Path
from datetime import datetime, timedelta
from odds_fetcher import fetch_nhl_odds, parse_odds, get_best_odds

CACHE_DIR = Path(__file__).parent / "cache"

def fetch_and_store_closing_lines(date_str=None):
    """
    Fetch closing lines for today's games.
    Call this 10 minutes before first game starts.
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    print(f"Fetching closing lines for {date_str}...")
    
    # Fetch current odds (these will be closing lines if timed right)
    raw_odds, _ = fetch_nhl_odds()
    parsed = parse_odds(raw_odds)
    
    # Store closing lines
    closing_lines = {}
    for game in parsed:
        game_key = f"{game['away_team']} @ {game['home_team']}"
        best_odds = get_best_odds(game)
        
        closing_lines[game_key] = {
            "timestamp": datetime.now().isoformat(),
            "moneyline": best_odds["moneyline"],
            "spread": best_odds["spread"],
            "total": best_odds["total"],
        }
    
    # Save to cache
    cache_path = CACHE_DIR / f"closing_lines_{date_str}.json"
    cache_path.write_text(json.dumps(closing_lines, indent=2, default=str))
    
    print(f"Stored closing lines for {len(closing_lines)} games")
    return closing_lines

def get_closing_line(game_key, date_str=None):
    """
    Get closing line for a specific game.
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    cache_path = CACHE_DIR / f"closing_lines_{date_str}.json"
    
    if not cache_path.exists():
        return None
    
    closing_lines = json.loads(cache_path.read_text())
    return closing_lines.get(game_key)
```

### Step 3: Add CLV Calculation (30 min)

```python
# In bet_tracker.py

from odds_fetcher import american_to_implied_prob
from closing_line_fetcher import get_closing_line

def calculate_clv(bet):
    """
    Calculate Closing Line Value for a bet.
    
    Returns:
        dict: {
            "clv": float (percentage),
            "bet_odds": int,
            "closing_odds": int,
            "bet_prob": float,
            "closing_prob": float,
        }
    """
    # Get closing line
    game_date = bet.get("game_date") or datetime.now().strftime("%Y-%m-%d")
    closing_line = get_closing_line(bet["game"], game_date)
    
    if not closing_line:
        return None
    
    # Determine which market
    bet_type = bet["bet_type"]
    pick = bet["pick"]
    
    # Extract closing odds for this specific bet
    if bet_type == "Moneyline":
        team = pick.split(" ")[0]
        if team in bet["game"].split(" @ ")[0]:  # Away team
            closing_odds = closing_line["moneyline"]["away"]["price"]
        else:  # Home team
            closing_odds = closing_line["moneyline"]["home"]["price"]
    
    elif bet_type == "Total":
        over_under = pick.split(" ")[0].lower()
        if over_under == "over":
            closing_odds = closing_line["total"]["over"]["price"]
        else:
            closing_odds = closing_line["total"]["under"]["price"]
    
    elif bet_type == "Spread":
        # Similar logic for spreads
        pass
    
    # Calculate CLV
    bet_odds = bet["odds"]
    bet_prob = american_to_implied_prob(bet_odds)
    closing_prob = american_to_implied_prob(closing_odds)
    
    clv = (closing_prob - bet_prob) * 100  # Convert to percentage
    
    return {
        "clv": clv,
        "bet_odds": bet_odds,
        "closing_odds": closing_odds,
        "bet_prob": bet_prob,
        "closing_prob": closing_prob,
    }
```

### Step 4: Update Performance Reports (30 min)

```python
# In bet_tracker.py - get_performance_stats()

def get_performance_stats():
    """
    Get performance statistics including CLV.
    """
    # ... existing code ...
    
    # Calculate CLV for all bets
    clv_data = []
    for bet_id, result in results.items():
        bet = result["bet"]
        clv_info = calculate_clv(bet)
        
        if clv_info:
            clv_data.append({
                "clv": clv_info["clv"],
                "grade": get_grade(bet["edge"]),
                "won": result["result"] == "won",
            })
    
    # Calculate CLV metrics
    if clv_data:
        avg_clv = sum(d["clv"] for d in clv_data) / len(clv_data)
        positive_clv_count = sum(1 for d in clv_data if d["clv"] > 0)
        positive_clv_rate = positive_clv_count / len(clv_data)
        
        # CLV by grade
        clv_by_grade = {}
        for grade in ["A", "B+", "B", "C+"]:
            grade_clv = [d["clv"] for d in clv_data if d["grade"] == grade]
            if grade_clv:
                clv_by_grade[grade] = {
                    "avg_clv": sum(grade_clv) / len(grade_clv),
                    "positive_rate": sum(1 for c in grade_clv if c > 0) / len(grade_clv),
                }
    
    return {
        # ... existing stats ...
        "clv": {
            "avg_clv": avg_clv,
            "positive_rate": positive_clv_rate,
            "by_grade": clv_by_grade,
        }
    }
```

---

## Usage Workflow

### Daily Workflow

1. **Morning:** Run analysis as usual
   ```bash
   python main.py --conservative
   ```
   - Generates bet recommendations
   - Stores odds at analysis time

2. **Pre-Game (10 min before first game):** Fetch closing lines
   ```bash
   python closing_line_fetcher.py
   ```
   - Fetches final odds
   - Stores as closing lines

3. **Post-Game:** Check results + CLV
   ```bash
   python bet_tracker.py --check
   ```
   - Updates bet results
   - Calculates CLV for each bet
   - Reports CLV metrics

### Weekly Review

```bash
python bet_tracker.py --check --days 7
```

Output:
```
PERFORMANCE SUMMARY (Last 7 Days)
==================================
Total bets: 15 | Won: 9 (60.0%) | ROI: +28.5%

CLOSING LINE VALUE (CLV)
=========================
Average CLV: +2.1% ✅
Positive CLV Rate: 73% (11/15 bets)

By Grade:
  [A  ] 3 bets | CLV: +4.2% | Positive: 100%
  [B+ ] 6 bets | CLV: +2.5% | Positive: 83%
  [B  ] 6 bets | CLV: +0.8% | Positive: 50%

CLV vs. Results:
  Positive CLV bets: 11 bets, 7 won (63.6%)
  Negative CLV bets: 4 bets, 2 won (50.0%)
```

---

## Success Metrics

**We'll know CLV tracking is working when:**

1. **Positive CLV on average** (target: +2% or better)
2. **High positive CLV rate** (target: 70%+ of bets)
3. **CLV correlates with grade** (A-grade should have highest CLV)
4. **CLV predicts profitability** (positive CLV bets should win more)

---

## Expected Results

Based on our current 60% win rate and +33% ROI, we expect:

- **Average CLV:** +2-3% (we're finding real edge)
- **Positive CLV Rate:** 70-75% (most bets beat closing)
- **A-grade CLV:** +4-5% (highest quality bets)
- **B+ grade CLV:** +2-3%
- **B grade CLV:** +1-2%

If we see these numbers, it validates our model is finding real edge, not just getting lucky.

---

## Automation Ideas

### Scheduled Closing Line Fetch

```bash
# Cron job to fetch closing lines automatically
# Run 10 minutes before typical game start times

# 6:50 PM ET (for 7:00 PM games)
50 18 * * * cd /path/to/nhl-betting && python closing_line_fetcher.py

# 9:50 PM ET (for 10:00 PM games)
50 21 * * * cd /path/to/nhl-betting && python closing_line_fetcher.py
```

### Automated CLV Reporting

```bash
# Daily CLV report at midnight
0 0 * * * cd /path/to/nhl-betting && python bet_tracker.py --check --report-clv
```

---

## Next Steps

1. **Implement Phase 1** (30 min) - Enhance analysis storage
2. **Implement Phase 2** (1 hour) - Create closing line fetcher
3. **Implement Phase 3** (30 min) - Add CLV calculation
4. **Implement Phase 4** (30 min) - Update reports
5. **Test** (30 min) - Verify on historical data
6. **Deploy** - Start tracking CLV on new bets

**Total Effort:** ~3 hours  
**Expected Impact:** HIGH - This is the validation we need

---

## Questions to Answer

Once CLV tracking is live:

1. **Is our edge real?** (Positive CLV = yes)
2. **Which bet grades have real edge?** (CLV by grade)
3. **Are we timing bets well?** (Early vs. late analysis)
4. **Should we adjust thresholds?** (If CLV is negative)
5. **Can we scale up stakes?** (If CLV is consistently positive)

---

**Status:** Ready to implement  
**Priority:** HIGH  
**Owner:** TBD  
**Timeline:** Can be done in one session
