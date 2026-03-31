## Adding Player-Level Data to NHL Lines

### What Player Data Can Improve:

**High Impact (5-10% accuracy boost):**
1. **Starting Goalies** - Biggest single factor
   - Save % difference between starters
   - Hot/cold streaks
   - Backup vs starter matchups

2. **Key Injuries** - Major impact
   - Star players out (McDavid, Matthews, etc.)
   - Top defensemen missing
   - Multiple injuries on same line

3. **Back-to-Back Games** - Fatigue factor
   - Teams on 2nd night of back-to-back lose ~5% more
   - Especially with travel

**Medium Impact (2-5% boost):**
4. **Top Scorer Form** - Recent production
   - Hot streaks (5+ points in last 3 games)
   - Cold streaks (0 points in last 5 games)

5. **Power Play Units** - Special teams
   - PP% with/without key players
   - Recent PP success rate

6. **Rest Days** - Recovery time
   - 0 days (back-to-back): -5% win rate
   - 1 day: normal
   - 2-3 days: +2% win rate
   - 4+ days: can be rusty

**Lower Impact (1-2% boost):**
7. **Travel Distance** - Jet lag
   - Cross-country games (LAK → BOS)
   - Time zone changes

8. **Line Combinations** - Chemistry
   - New lines vs established
   - Call-ups vs regulars

### Implementation Status:

✅ **Created**: `player_data.py` - Fetches rosters and goalie info
✅ **Created**: `ml_model_enhanced.py` - ML model with player features
⏳ **TODO**: Integrate into main.py
⏳ **TODO**: Add goalie stats scraping
⏳ **TODO**: Add injury tracking

### Quick Win: Starting Goalies

The easiest and highest-impact addition is **starting goalie stats**:

```python
# Example impact:
Elite goalie (Hellebuyck, Shesterkin): +8% win probability
Average goalie: baseline
Backup goalie: -5% win probability

# Matchup examples:
Elite vs Backup: +13% swing!
Elite vs Elite: Minimal impact
Backup vs Backup: Minimal impact
```

### Data Sources:

**Free APIs:**
- NHL API (api-web.nhle.com) - Rosters, basic stats ✅
- Daily Faceoff - Starting goalies (scraping needed)
- NHL.com injury reports (scraping needed)

**Paid APIs (Better Data):**
- The Sports DB - Player stats
- API-Sports NHL - Comprehensive player data
- Sportradar - Professional-grade data

### How to Integrate:

**Option 1: Manual Updates (Quick)**
```python
# Add to config.json
{
    "odds_api_key": "...",
    "starting_goalies": {
        "2026-03-01": {
            "TOR": "Joseph Woll",
            "BOS": "Jeremy Swayman"
        }
    }
}
```

**Option 2: Automated Scraping (Better)**
- Scrape Daily Faceoff for confirmed starters
- Update 2-3 hours before games
- Cache for the day

**Option 3: Paid API (Best)**
- Real-time updates
- Historical goalie stats
- Injury reports included

### Feature Importance (Expected):

Based on hockey analytics research:

```
1. Starting Goalie Save %: 15-20% importance
2. Team Win %: 12-15%
3. Recent Form: 10-12%
4. Key Injuries: 8-10%
5. Back-to-Back: 6-8%
6. Goals For/Against: 5-7% each
7. Rest Days: 3-5%
8. Home/Away Split: 3-5%
... (other features)
```

### Next Steps:

**Phase 1: Goalie Stats (Highest ROI)**
1. Scrape Daily Faceoff for starting goalies
2. Add goalie save % and GAA to features
3. Retrain model with goalie data
4. Expected improvement: +5-8% accuracy

**Phase 2: Injuries**
1. Track major injuries (star players)
2. Add injury impact score (0-3)
3. Expected improvement: +2-4% accuracy

**Phase 3: Situational**
1. Add back-to-back indicator
2. Add rest days
3. Add travel distance
4. Expected improvement: +2-3% accuracy

**Total Expected Improvement: +9-15% accuracy**

### Example Enhanced Prediction:

**Before (Team Stats Only):**
```
TOR @ BOS
Model: BOS 58% (based on team stats)
```

**After (With Player Data):**
```
TOR @ BOS
- BOS starting Swayman (.920 SV%) vs TOR backup (.895 SV%)
- TOR missing Matthews (injury)
- BOS on 2 days rest, TOR on back-to-back

Enhanced Model: BOS 68% (+10% from player factors!)
```

### Want to Implement?

I can help you:
1. Set up goalie scraping from Daily Faceoff
2. Integrate player features into the ML model
3. Add injury tracking
4. Create a simple UI to input starting goalies manually

Which would you like to start with?
