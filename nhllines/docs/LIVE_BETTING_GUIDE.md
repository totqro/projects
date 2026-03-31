# Live Betting Implementation Guide

## Current Status
The system currently analyzes **pre-game odds only**. Live betting requires additional data sources and modeling.

## What's Needed for Live Betting

### 1. Live Game Data
- Current score
- Time remaining (period, minutes, seconds)
- Current game state (power play, empty net, etc.)
- Shot counts, faceoff wins, etc.

**Source:** NHL API provides live game data
- Endpoint: `https://api-web.nhle.com/v1/gamecenter/{gameId}/play-by-play`
- Updates every ~10 seconds during games

### 2. Live Odds Feed
- Odds that update during the game
- Most sportsbooks update odds every 30-60 seconds during play

**Challenge:** The Odds API (our current source) only provides pre-game odds. Live odds require:
- Premium API subscription ($$$)
- Or web scraping (against ToS for most books)
- Or manual entry

### 3. In-Game Probability Model

The pre-game model doesn't work for live betting. Need to factor in:

#### Score Differential
- Team up by 2+ goals: Much higher win probability
- Team down by 1 in 3rd period: Lower but not zero (empty net strategy)

#### Time Remaining
- 5 minutes left vs 55 minutes left makes huge difference
- Empty net situations (last 2 minutes when trailing)

#### Game State
- Power play: ~20% boost to scoring probability
- Penalty kill: Defensive focus
- Goalie pulled: High variance situation

### 4. Live Betting Model Formula

```python
def calculate_live_win_probability(
    current_score_diff,  # Home - Away
    time_remaining_seconds,
    period,
    game_state,  # 'even', 'pp', 'pk', 'empty_net'
    pre_game_home_win_prob
):
    """
    Adjust pre-game probability based on current game state.
    """
    
    # Base adjustment from score
    if current_score_diff > 0:
        # Home team leading
        score_boost = min(0.4, current_score_diff * 0.15)
    else:
        score_boost = max(-0.4, current_score_diff * 0.15)
    
    # Time decay - less time = more certain outcome
    time_factor = time_remaining_seconds / 3600  # 0 to 1
    score_boost *= (1 - time_factor * 0.5)  # Score matters more late
    
    # Game state adjustments
    if game_state == 'pp':
        score_boost += 0.05  # Power play boost
    elif game_state == 'empty_net':
        if current_score_diff < 0:
            # Trailing team pulled goalie - high variance
            score_boost -= 0.1
    
    # Combine with pre-game probability
    live_prob = pre_game_home_win_prob + score_boost
    
    # Clamp to valid range
    return max(0.01, min(0.99, live_prob))
```

## Implementation Steps

### Phase 1: Data Collection (1-2 hours)
1. Create `live_game_tracker.py` to fetch live game data from NHL API
2. Store current score, time, period for each active game
3. Cache updates every 30 seconds

### Phase 2: Live Odds (Requires Premium API or Manual Entry)
1. Option A: Subscribe to premium live odds API (~$100-500/month)
2. Option B: Manual entry interface for live odds
3. Option C: Scrape from legal sources (check ToS)

### Phase 3: Live Model (2-3 hours)
1. Implement `live_probability_model.py`
2. Adjust pre-game probabilities based on:
   - Score differential
   - Time remaining
   - Game state (PP, PK, empty net)
3. Calculate live EV using adjusted probabilities

### Phase 4: UI Updates (1 hour)
1. Add "Live Games" section to website
2. Show current score, time, live odds
3. Display live +EV opportunities
4. Auto-refresh every 30 seconds

## Example Live Betting Scenario

**Pre-game:**
- TOR vs BOS
- Pre-game model: TOR 55% win probability
- Pre-game odds: TOR -120

**Live (End of 2nd Period):**
- Score: TOR 2, BOS 1
- Time: 20:00 remaining (3rd period)
- Live odds: TOR -250 (80% implied)

**Live Model Calculation:**
```
Score diff: +1 (TOR leading)
Time factor: 20 min / 60 min = 0.33
Score boost: +1 * 0.15 * (1 - 0.33 * 0.5) = +0.125

Live probability: 0.55 + 0.125 = 0.675 (67.5%)
Market implied: 0.80 (80%)

Edge: 67.5% - 80% = -12.5% (NO BET - market overvalues TOR)
```

## Cost-Benefit Analysis

### Costs:
- Development time: 4-6 hours
- Live odds API: $100-500/month (or manual entry)
- Monitoring: Need to watch games actively

### Benefits:
- More betting opportunities (5-10 per game)
- Can capitalize on market overreactions
- Higher edges during volatile moments (goals, penalties)

### Recommendation:
**Start with pre-game betting** (current system) because:
1. Pre-game model is already profitable (60% win rate, +33% ROI)
2. Live betting requires constant monitoring
3. Live odds APIs are expensive
4. Pre-game bets are easier to manage

**Consider live betting later** if:
1. Pre-game system proves consistently profitable over 100+ bets
2. You have time to actively monitor games
3. You're willing to pay for live odds API or manually enter odds

## Future Enhancement: Semi-Live Betting

A middle ground approach:
1. Analyze games at **period breaks** (intermissions)
2. Use updated score + time remaining
3. Check if live odds have overreacted
4. Place bets before next period starts

This gives you:
- Live betting advantages (updated probabilities)
- Without constant monitoring (only 2-3 checks per game)
- Can use free NHL API for scores
- Manual odds entry is feasible (only 2-3 times per game)

## Code Skeleton for Future Implementation

```python
# live_game_tracker.py
def get_live_games():
    """Fetch all games currently in progress."""
    # NHL API: /schedule endpoint with date=today
    # Filter for games with status = 'Live'
    pass

def get_live_game_state(game_id):
    """Get current score, time, period for a game."""
    # NHL API: /gamecenter/{gameId}/play-by-play
    return {
        'home_score': 2,
        'away_score': 1,
        'period': 3,
        'time_remaining': '12:34',
        'game_state': 'even'  # or 'pp', 'pk', 'empty_net'
    }

# live_model.py
def calculate_live_edge(game_state, live_odds, pre_game_model):
    """Calculate edge for live betting opportunity."""
    live_prob = adjust_probability_for_game_state(
        pre_game_model['home_win_prob'],
        game_state
    )
    
    market_prob = odds_to_probability(live_odds)
    edge = live_prob - market_prob
    
    return edge
```

## Conclusion

Live betting is a powerful feature but requires:
1. Additional data sources (live odds)
2. More complex modeling
3. Active monitoring during games

**Recommendation:** Master pre-game betting first, then consider live betting as an advanced feature once the system proves profitable over 100+ bets.

Current system performance (60% win rate, +33% ROI) suggests pre-game betting alone is sufficient for profitability.
