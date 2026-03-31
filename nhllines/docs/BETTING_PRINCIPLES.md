# NHL Betting Model - Core Principles & Best Practices

**Last Updated:** March 7, 2026

This document outlines the fundamental principles that guide our NHL betting model development and decision-making.

---

## 1. Data Foundation First

**Principle:** Everything depends on clean, reliable data. Before any modeling, you need solid foundations.

### Required Data Sources

#### Historical Game Results
- ✅ **Implemented:** `nhl_data.py` fetches game results from NHL API
- ✅ Scores, OT/SO outcomes tracked
- ✅ 90-day rolling window (567 games currently)
- ✅ Team stats per game available

#### Historical Odds
- ✅ **Implemented:** The Odds API integration (`odds_fetcher.py`)
- ✅ Current lines fetched in real-time
- ✅ Multiple bookmakers tracked (theScore, FanDuel, DraftKings, etc.)
- ⚠️ **Gap:** No historical closing line data stored
- 📝 **Future:** Store opening vs. closing line movements

#### Team Stats Per Game
- ✅ **Implemented:** Comprehensive stats tracked
  - Shots, goals for/against
  - Win percentage, points percentage
  - Home/road splits
  - Recent form (last 10 games)
- ✅ Advanced stats: Corsi, xGF, PP%, PK% (`advanced_stats.py`)
- ✅ Goalie stats: SV%, GAA, quality starts (`goalie_tracker.py`)

### Why Closing Lines Matter

**The closing line is the most efficient price** — it incorporates all available information including:
- Sharp money movement
- Late-breaking news (injuries, goalies)
- Market consensus

**Closing Line Value (CLV)** is the gold standard metric:
- If you consistently beat the closing line, you have real edge
- More honest evaluation than win rate alone
- Win rate can be misleading due to variance

**Current Status:**
- ⚠️ We don't track CLV yet (no historical closing lines stored)
- ✅ We do track market consensus (no-vig probabilities)
- 📝 **Action Item:** Implement CLV tracking for validation

---

## 2. "Similar Games" Definition

**Principle:** The core intellectual challenge is defining what makes games "similar."

### Current Implementation

Our similarity model (`model.py`) uses:

1. **Team Quality Differential**
   - Win percentage difference
   - Points percentage difference
   - Goal differential

2. **Recent Form**
   - Last 10 games performance
   - Goals for/against trends
   - Win streaks/slumps

3. **Home/Away Context**
   - Home team home record
   - Away team road record
   - Home ice advantage

4. **Head-to-Head History**
   - Recent matchups between teams
   - Historical performance patterns

### Similarity Features (Prioritized)

✅ **Currently Used:**
- Rest days (back-to-back detection)
- Home/away splits
- Implied total bucket (via market odds)
- Team form (last 10 games)
- Goalie quality

📝 **Could Add:**
- Travel distance/timezone changes
- Divisional rivalry flags
- Playoff positioning stakes
- Time of season context

### Philosophy: Start Simple, Add Complexity

We started with basic team stats and have progressively added:
1. Recent form weighting
2. Goalie quality scores
3. Home/road splits
4. Injury impact
5. Advanced stats (Corsi, xGF)

**Result:** 60% win rate, +33% ROI validates the approach.

---

## 3. Line Value, Not Just Predicted Outcome

**Principle:** The goal isn't to predict the winner — it's to find mispriced lines.

### Expected Value (EV) Focus

A model that says "Team A wins 58% of the time" is only useful if the line implies <58%.

**Our Implementation:**

```python
# From ev_calculator.py
def calculate_ev(true_prob, odds, stake):
    """
    Calculate expected value of a bet.
    
    EV = (true_prob × profit) - ((1 - true_prob) × stake)
    """
    decimal_odds = american_to_decimal(odds)
    profit_if_win = stake * (decimal_odds - 1)
    loss_if_lose = stake
    
    ev = (true_prob * profit_if_win) - ((1 - true_prob) * loss_if_lose)
    edge = ev / stake
    
    return ev, edge
```

### Output Format

✅ **We output:**
- Expected value per bet (in dollars)
- Edge percentage (EV / stake)
- Bet grade (A, B+, B, C+ based on edge)
- Kelly criterion stake recommendation

✅ **We DON'T just output:**
- "Team A will win" (not actionable)
- Win probability alone (meaningless without odds)

### Conservative Mode

✅ **Implemented:** 3%+ edge minimum
- Filters out marginal bets
- Focuses on highest-quality opportunities
- Reduces variance

---

## 4. Closing Line Value (CLV) as North Star Metric

**Principle:** If you consistently beat the closing line, you have real edge.

### Why CLV > Win Rate

**Win Rate Issues:**
- Subject to variance (small samples)
- Can be misleading (lucky streaks)
- Doesn't measure true skill

**CLV Advantages:**
- Immediate feedback (no waiting for results)
- Measures edge detection skill
- Variance-resistant metric
- Industry standard for sharp bettors

### Current Status

⚠️ **Not Yet Implemented:**
- We don't store opening lines
- We don't track closing lines
- We can't calculate CLV retrospectively

✅ **What We Do Track:**
- Market consensus (no-vig probabilities)
- Our model's predicted probabilities
- Actual bet outcomes
- Win rate and ROI by grade

📝 **Action Item:** Build CLV tracking system
1. Store odds at time of analysis
2. Fetch closing lines before game start
3. Calculate CLV for each bet
4. Report CLV alongside win rate

---

## Features We Want (Checklist)

### Team Context

| Feature | Status | Implementation |
|---------|--------|----------------|
| Home/away record | ✅ | `team_splits.py` |
| Back-to-back fatigue | ✅ | `scraper.py` (player_data) |
| Days of rest differential | ✅ | `scraper.py` |
| Travel distance/timezone | ⚠️ | Not implemented |

### Goalie (Huge in Hockey)

| Feature | Status | Implementation |
|---------|--------|----------------|
| Starting goalie confirmed | ✅ | `goalie_tracker.py` (DailyFaceoff scraper) |
| Last 10-game SV%, GAA | ✅ | `goalie_tracker.py` (recent form) |
| Career SV% vs. opponent | ⚠️ | Not implemented |
| Quality score (0-100) | ✅ | `goalie_tracker.py` |

### Offensive/Defensive Efficiency

| Feature | Status | Implementation |
|---------|--------|----------------|
| 5v5 Corsi% | ✅ | `advanced_stats.py` |
| Expected goals (xGF, xGA) | ✅ | `advanced_stats.py` |
| Power play % | ✅ | `advanced_stats.py` |
| Penalty kill % | ✅ | `advanced_stats.py` |

### Recent Form

| Feature | Status | Implementation |
|---------|--------|----------------|
| Last 5-10 games weighted | ✅ | `nhl_data.py` (get_team_recent_form) |
| Win streaks/slumps | ✅ | Implicit in form calculation |
| Goals for/against trends | ✅ | Tracked in recent form |

### Line Movement

| Feature | Status | Implementation |
|---------|--------|----------------|
| Opening vs. current spread | ⚠️ | Not tracked |
| Sharp money signals | ⚠️ | Not tracked |
| Public % vs. line direction | ⚠️ | Not available |

### Game Context

| Feature | Status | Implementation |
|---------|--------|----------------|
| Divisional rivalry flag | ⚠️ | Not implemented |
| Playoff positioning stakes | ⚠️ | Not implemented |
| Time of season | ⚠️ | Not implemented |
| Injury impact | ✅ | `injury_tracker.py` |

---

## What We Punt on (For Now)

### 1. Player-Level Injury Modeling
**Status:** ⚠️ Partially implemented
- We track injuries (`injury_tracker.py`)
- We calculate impact scores
- But we don't model individual player contributions deeply

**Why Punt:**
- Complex and noisy
- Market already prices this in efficiently
- Our optimization showed manual adjustments hurt performance

**Lesson Learned:** Manual injury adjustments caused 48-62% negative impact on win rate. The market is efficient at pricing player-level factors.

### 2. Neural Nets / Complex ML Early On
**Status:** ✅ Using gradient boosting (XGBoost)
- Not using deep learning
- Logistic regression + good features often beats it
- Simpler models are more interpretable

**Philosophy:** Start simple, add complexity only when needed.

### 3. Live/In-Game Betting
**Status:** ✅ Explicitly filtered out
- `main.py` filters games that started >30 min ago
- Live betting is a different beast entirely
- Requires real-time data feeds
- Different edge opportunities

**Why Punt:**
- Pre-game analysis is hard enough
- Live odds move too fast
- Need different infrastructure

---

## Model Evolution & Lessons Learned

### Phase 1: Basic Similarity Model
- Used team stats + recent form
- Found similar historical games
- Estimated probabilities from outcomes
- **Result:** 70% win rate initially

### Phase 2: ML Enhancement
- Added XGBoost models
- Trained on 567 historical games
- Blended with similarity model (55% similarity, 45% ML)
- **Result:** Improved predictions

### Phase 3: Hybrid Model (Failed)
- Added manual adjustments for:
  - Goalie quality (+/- 3%)
  - Injuries (-2% per 5 impact)
  - Back-to-back (-2%)
  - Home/road splits (+/- 2%)
- **Result:** Win rate dropped to 47.4% ❌

### Phase 4: Optimization (Current)
- Removed ALL manual adjustments
- Returned to pure ML + similarity blend
- Trust the data, not intuition
- **Result:** 60% win rate, +33% ROI ✅

### Key Insight

**The market already prices in player-level factors efficiently.**

Our edge comes from:
1. Better team-level statistical modeling
2. Finding market inefficiencies in odds
3. Proper bankroll management

NOT from trying to be smarter than the market about injuries and fatigue.

---

## Performance Metrics

### Current Performance (35 bets tracked)
- **Win Rate:** 60%
- **ROI:** +33%
- **Best Day:** March 6 (5-1, 83.3%)
- **Average Edge:** 5.36%

### By Grade
- **A-grade (7%+ edge):** Limited sample
- **B+ grade (4-7% edge):** Strong performance
- **B grade (3-4% edge):** Solid performance
- **C+ grade (<3% edge):** Not recommended in conservative mode

### What We Track
✅ Win rate by grade
✅ ROI by grade
✅ Total profit/loss
✅ Bet volume over time
✅ Analysis history (30-day rolling)

⚠️ What We Don't Track (Yet)
- Closing line value (CLV)
- Opening vs. closing line movement
- Public betting percentages
- Sharp money indicators

---

## Data Pipeline

### Current Sources

1. **NHL API** (Free)
   - Game results and schedules
   - Team standings
   - Player stats
   - Goalie stats
   - ✅ Reliable and comprehensive

2. **The Odds API** (500 requests/month free)
   - Current betting lines
   - Multiple bookmakers
   - Moneyline, spreads, totals
   - ✅ 3 API keys configured (1,386 requests remaining)

3. **DailyFaceoff.com** (Scraped)
   - Starting goalie confirmations
   - Confidence levels
   - ✅ Updated every 2 hours

4. **Natural Stat Trick** (Optional)
   - Advanced stats (Corsi, xGF)
   - 5v5 metrics
   - ⚠️ Not currently integrated

### Data Freshness

| Data Type | Cache Duration | Update Frequency |
|-----------|----------------|------------------|
| Game results | 24 hours | Daily |
| Standings | 24 hours | Daily |
| Odds | 30 minutes | Real-time |
| Goalie starters | 2 hours | Multiple times daily |
| Injury reports | 6 hours | Multiple times daily |
| Advanced stats | 24 hours | Daily |

---

## Recommended Next Steps

### High Priority

1. **Implement CLV Tracking**
   - Store odds at analysis time
   - Fetch closing lines
   - Calculate and report CLV
   - Use as primary validation metric

2. **Line Movement Tracking**
   - Store opening lines
   - Track line movement direction
   - Identify sharp money signals
   - Correlate with our predictions

3. **Enhanced Backtesting**
   - Test model on historical data
   - Calculate historical CLV
   - Validate edge detection
   - Optimize blending weights

### Medium Priority

4. **Game Context Features**
   - Divisional rivalry flags
   - Playoff positioning
   - Season timing
   - Rest advantage quantification

5. **Travel/Timezone Modeling**
   - Calculate travel distance
   - Timezone change impact
   - West coast road trips
   - Quantify fatigue beyond B2B

6. **Public Betting Data**
   - Integrate public % data
   - Fade the public opportunities
   - Contrarian indicators
   - Sharp vs. square money

### Low Priority

7. **Live Betting Infrastructure**
   - Real-time data feeds
   - In-game modeling
   - Different edge opportunities
   - Requires significant investment

8. **Deep Learning Exploration**
   - Only if current model plateaus
   - Neural nets for pattern recognition
   - Ensemble methods
   - Interpretability trade-offs

---

## Philosophy Summary

### Core Beliefs

1. **Data quality > Model complexity**
   - Clean data beats fancy algorithms
   - Simple models with good features win

2. **Market efficiency is real**
   - Don't fight the closing line
   - Player-level factors are priced in
   - Find structural edges, not information edges

3. **Edge detection > Outcome prediction**
   - Focus on EV, not win probability
   - CLV is the north star metric
   - Variance is inevitable, edge is what matters

4. **Start simple, add complexity**
   - Validate each addition
   - Remove what doesn't work
   - Trust the data, not intuition

5. **Bankroll management matters**
   - Kelly criterion for sizing
   - Conservative mode for safety
   - Long-term sustainability

### What Makes Us Different

**We don't:**
- Chase big parlays
- Bet on every game
- Override the model with "gut feelings"
- Ignore the market consensus

**We do:**
- Focus on +EV opportunities
- Track performance rigorously
- Optimize based on data
- Respect market efficiency
- Manage bankroll conservatively

---

## Success Metrics

### Short-Term (Weekly)
- ✅ Positive ROI
- ✅ 55%+ win rate on quality bets
- ✅ Consistent edge detection
- ⚠️ CLV > 0 (not yet tracked)

### Medium-Term (Monthly)
- ✅ 60%+ win rate sustained
- ✅ 25%+ ROI sustained
- ⚠️ Positive CLV across all bets
- ✅ Model improvements validated

### Long-Term (Season)
- 📊 Beat closing lines consistently
- 📊 Profitable across all bet grades
- 📊 Scalable to higher stakes
- 📊 Adaptable to market changes

---

## Conclusion

Our NHL betting model is built on solid principles:
1. **Data foundation first** - Clean, reliable data sources
2. **Similar games approach** - Smart similarity definition
3. **EV focus** - Line value, not just predictions
4. **CLV as north star** - The ultimate validation metric

We've learned that **market efficiency is real** — manual adjustments hurt more than they help. Our edge comes from better statistical modeling and finding structural inefficiencies, not from trying to outsmart the market on player-level factors.

**Current status:** 60% win rate, +33% ROI validates our approach. Next step is implementing CLV tracking to measure our true edge.

---

**Remember:** The goal isn't to predict every game correctly. The goal is to find mispriced lines and exploit them consistently over time.
