# NHL Betting Model - Data Enhancement Plan

## Current Data Sources ✅
1. **Team Stats** (NHL API - Free)
   - Standings, wins/losses, points
   - Goals for/against per game
   - Home/road records
   - Last 10 games record

2. **Historical Games** (NHL API - Free)
   - Game scores (90 days back)
   - Win/loss outcomes
   - Total goals

3. **Basic Player Data** (NHL API - Free)
   - Rest days
   - Back-to-back games
   - Team rosters

4. **Live Odds** (The Odds API - Paid)
   - Moneylines, spreads, totals
   - Multiple sportsbooks

## Critical Missing Data 🔴

### 1. **Starting Goalies** (HIGHEST PRIORITY)
**Impact:** Goalies account for 40-50% of game outcomes
**Current Status:** Not available
**What We Need:**
- Confirmed starting goalies (announced ~1 hour before game)
- Goalie season stats:
  - Save percentage (SV%)
  - Goals against average (GAA)
  - Quality starts
  - Recent form (last 5 starts)
  - Home vs road splits
  - Performance vs specific teams

**Potential Free Sources:**
- DailyFaceoff.com (scraping)
- NHL.com game preview pages
- Twitter/X NHL beat reporters
- LeftWingLock.com

**API Opportunity:** 
Create an API that aggregates goalie confirmations from multiple sources with confidence scores.

---

### 2. **Injuries & Lineup Changes** (HIGH PRIORITY)
**Impact:** Star player absences can swing odds by 5-10%
**Current Status:** Not tracked
**What We Need:**
- Injury reports (IR, DTD, Out, Questionable)
- Player importance score (1st line vs 4th line)
- Expected return dates
- Lineup scratches (healthy scratches, load management)

**Potential Free Sources:**
- NHL.com injury reports
- ESPN NHL injuries page
- Team Twitter accounts
- CapFriendly (RIP - now NHL owned)

**API Opportunity:**
Real-time injury tracking with impact scoring (0-10 scale based on player TOI, points, etc.)

---

### 3. **Advanced Goalie Metrics** (HIGH PRIORITY)
**Impact:** Better goalie evaluation = better predictions
**What We Need:**
- Goals Saved Above Expected (GSAx)
- High-danger save percentage
- Rebound control metrics
- Workload (shots faced per game)
- Performance on rest vs back-to-back

**Potential Sources:**
- Natural Stat Trick (free, scrapable)
- MoneyPuck.com (free API)
- Evolving-Hockey (paid but worth it)

---

### 4. **Shot Quality & Expected Goals (xG)** (MEDIUM PRIORITY)
**Impact:** Better than just goals for/against
**What We Need:**
- Expected goals for (xGF) per game
- Expected goals against (xGA) per game
- Shooting percentage vs expected
- High-danger chances for/against

**Potential Free Sources:**
- MoneyPuck.com (has free xG data)
- Natural Stat Trick
- HockeyStatCards.com

**API Opportunity:**
Aggregate xG data from multiple models and provide team-level metrics.

---

### 5. **Special Teams Performance** (MEDIUM PRIORITY)
**Impact:** Power plays can swing totals significantly
**What We Need:**
- Power play % (current)
- Penalty kill % (current)
- PP opportunities per game
- Recent PP/PK trends (last 10 games)

**Current Status:** Partially available via NHL API
**Enhancement Needed:** Recent form tracking, situational splits

---

### 6. **Line Combinations** (MEDIUM PRIORITY)
**Impact:** Line chemistry affects scoring
**What We Need:**
- Current line combinations (F1, F2, F3, F4)
- Defense pairings (D1, D2, D3)
- Line performance metrics (goals/60, xG/60)
- Recent line changes

**Potential Sources:**
- DailyFaceoff.com line combinations
- Natural Stat Trick line stats
- NHL.com depth charts

---

### 7. **Travel & Fatigue** (LOW-MEDIUM PRIORITY)
**Impact:** 2-3% edge in specific situations
**What We Need:**
- Travel distance (miles traveled)
- Time zone changes
- Days since last game (already have)
- Games in last X days (schedule density)

**Current Status:** Partially available (rest days)
**Enhancement:** Add travel distance calculation

---

### 8. **Referee Assignments** (LOW PRIORITY)
**Impact:** Some refs call more penalties
**What We Need:**
- Assigned referee for each game
- Referee penalty call rate
- Impact on total goals (more PPs = more goals)

**Potential Sources:**
- ScoutingTheRefs.com
- NHL.com game sheets

---

### 9. **Weather (Outdoor Games Only)** (LOW PRIORITY)
**Impact:** Minimal (only for outdoor games)
**What We Need:**
- Temperature, wind, precipitation for outdoor games

---

### 10. **Betting Market Movement** (MEDIUM PRIORITY)
**Impact:** Sharp money indicators
**What We Need:**
- Line movement tracking (opening vs current)
- Bet percentage vs money percentage
- Steam moves (sudden line shifts)
- Reverse line movement

**Potential Sources:**
- Action Network (paid)
- Odds Shark (free but limited)
- Your own tracking via The Odds API

---

## Recommended Free APIs to Build 🛠️

### API #1: **Goalie Tracker API** (HIGHEST VALUE)
**Endpoints:**
```
GET /api/goalies/today
- Returns confirmed starting goalies for today's games
- Includes confidence score (confirmed, likely, probable, unknown)

GET /api/goalies/{team}/stats
- Returns season stats for team's goalies
- SV%, GAA, recent form, splits

GET /api/goalies/{goalie_id}/recent
- Last 5 starts with results
```

**Data Sources:**
- Scrape DailyFaceoff every 2 hours
- Monitor NHL beat reporter Twitter accounts
- Parse NHL.com game previews
- Aggregate with confidence scoring

**Value:** This alone could improve model accuracy by 10-15%

---

### API #2: **Injury Impact API**
**Endpoints:**
```
GET /api/injuries/today
- Returns all injuries affecting today's games
- Includes impact score (0-10)

GET /api/injuries/{team}
- Current injury report for team
- Player importance, expected return

GET /api/lineup-changes/{game_id}
- Last-minute scratches and lineup changes
```

**Data Sources:**
- NHL.com injury reports
- ESPN injuries
- Team Twitter accounts
- Reddit r/hockey game threads

**Value:** Catch 5-10% of games where key players are out

---

### API #3: **Advanced Stats Aggregator**
**Endpoints:**
```
GET /api/advanced/{team}/current
- xGF, xGA, HDCF, HDCA
- PP%, PK%
- Recent form (last 10 games)

GET /api/advanced/{team}/splits
- Home vs road
- vs specific opponents
- With/without key players
```

**Data Sources:**
- MoneyPuck.com (free API exists)
- Natural Stat Trick (scraping)
- NHL API (basic stats)

**Value:** Better team evaluation than basic stats

---

### API #4: **Line Movement Tracker**
**Endpoints:**
```
GET /api/lines/{game_id}/movement
- Opening line vs current
- Timestamp of major moves
- Bet % vs money %

GET /api/lines/steam-moves
- Recent sharp action indicators
```

**Data Sources:**
- Your own tracking via The Odds API
- Store historical odds every 30 minutes
- Calculate movement patterns

**Value:** Identify sharp vs public money

---

## Implementation Priority 🎯

### Phase 1 (Immediate - Highest ROI)
1. ✅ **Goalie Tracker API** - Build this first
2. ✅ **Injury Impact API** - Second priority
3. Integrate both into ML model

**Expected Improvement:** +10-15% accuracy

### Phase 2 (Next Month)
1. Advanced stats integration (xG, HDCF)
2. Line combinations tracking
3. Enhanced special teams data

**Expected Improvement:** +5-8% accuracy

### Phase 3 (Future)
1. Line movement tracking
2. Referee impact analysis
3. Travel/fatigue modeling

**Expected Improvement:** +3-5% accuracy

---

## Data Quality Metrics 📊

Track these for each data source:
- **Availability:** % of games with data
- **Accuracy:** % correct predictions
- **Timeliness:** How early is data available
- **Reliability:** Uptime/consistency

---

## Cost-Benefit Analysis 💰

### Free Data (Scraping)
- **Cost:** Development time + server costs (~$20/month)
- **Benefit:** 10-20% accuracy improvement
- **ROI:** Excellent

### Paid Data Services
- **MoneyPuck Pro:** $0 (free tier sufficient)
- **Evolving-Hockey:** ~$50/month (advanced metrics)
- **Action Network:** ~$100/month (line movement)
- **Total:** ~$150/month

**Break-even:** If model improves ROI by 2-3%, pays for itself with $100-200 in bets per day

---

## Next Steps 🚀

1. **Build Goalie Tracker API** (Week 1)
   - Set up scraping infrastructure
   - Create confidence scoring system
   - Test with historical data

2. **Build Injury Impact API** (Week 2)
   - Aggregate injury sources
   - Create player importance scoring
   - Integrate with model

3. **Integrate Advanced Stats** (Week 3)
   - Connect to MoneyPuck API
   - Add xG features to ML model
   - Retrain with new features

4. **Backtest Improvements** (Week 4)
   - Test on historical data
   - Measure accuracy improvement
   - Adjust feature weights

---

## Questions for You 🤔

1. **Which API should we build first?** (I recommend Goalie Tracker)
2. **Do you have server infrastructure?** (Need for scraping/caching)
3. **Comfortable with web scraping?** (BeautifulSoup, Selenium)
4. **Budget for paid data?** (Optional but helpful)
5. **Time commitment?** (Building APIs takes 5-10 hours each)

Let me know which direction you want to go and I can help build it!
