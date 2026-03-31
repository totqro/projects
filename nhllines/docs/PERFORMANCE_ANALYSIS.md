# Performance Analysis - Hybrid Model

**Date:** March 6, 2026  
**Issue:** Win rate dropped from 70% to 47.4% after hybrid model deployment

---

## The Numbers

### Before Hybrid Model (March 1-2)
- **Bets:** 10
- **Record:** 7-3 (70.0% win rate)
- **ROI:** +53.2%
- **Average edge:** 4.9%

### After Hybrid Model (March 3-6)
- **Bets:** 19
- **Record:** 9-10 (47.4% win rate) ❌
- **ROI:** +1.8%
- **Average edge:** 5.6%

---

## What's Happening

### 1. **A-grade and B+ bets are failing**

**A-grade:**
- Before: 2/2 (100%) ✅
- After: 2/4 (50%) ❌

**B+ grade:**
- Before: 2/2 (100%) ✅
- After: 2/7 (28.6%) ❌❌

**B grade:**
- Before: 3/6 (50%)
- After: 4/6 (66.7%) ✅ (Actually improved!)

### 2. **We're betting more volume**
- 10 bets → 19 bets (+90%)
- Finding more "opportunities" but they're not hitting

### 3. **Higher edges aren't translating to wins**
- Average edge increased: 4.9% → 5.6%
- But win rate dropped: 70% → 47.4%
- This suggests **overconfidence** in adjustments

### 4. **Sample size is still small**
- Only 19 bets after hybrid
- Could be variance, but the pattern is concerning

---

## Root Cause Analysis

### Problem: Adjustment Weights May Be Too Aggressive

The hybrid model applies these adjustments:
```python
hot_goalie = +3%      # .930+ SV%
cold_goalie = -3%     # .890- SV%
goalie_quality = +2%  # per 10 points
injuries = -2%        # per 5 impact
back_to_back = -2%    # fatigue
strong_home = +2%     # 70%+ win rate
```

**These might be too strong**, causing us to:
1. Overestimate underdogs with "good" factors
2. Find +EV where there isn't real value
3. Bet on marginal situations

### Evidence:

**March 4 (0-3 day):**
- All 3 bets lost
- Likely had strong adjustments that created false edges

**March 5 (1-2 day):**
- NYI ML (A-grade, 7.8% edge) - LOST
  - Had -4.5% adjustment for LAK (weak home, cold goalie)
  - Model was too confident

---

## Is This Variance or a Real Problem?

### Arguments for "Just Variance":
1. **Small sample:** Only 19 bets
2. **Expected variance:** Even 70% win rate has losing streaks
3. **B-grade bets improved:** 50% → 66.7%
4. **Still profitable:** +$0.19 (barely, but positive)

### Arguments for "Real Problem":
1. **Consistent pattern:** A and B+ grades both failing
2. **Opposite of expected:** Higher edges should = better results
3. **Volume increase:** Finding more bets suggests looser criteria
4. **Specific failure mode:** High-adjustment bets are losing

---

## Recommended Actions

### Option 1: Reduce Adjustment Weights (Recommended) ✅

**Cut all adjustments in half:**
```python
hot_goalie = +1.5%    # was +3%
cold_goalie = -1.5%   # was -3%
goalie_quality = +1%  # was +2%
injuries = -1%        # was -2%
back_to_back = -1%    # was -2%
strong_home = +1%     # was +2%
```

**Rationale:**
- More conservative = fewer false positives
- Still captures the factors but less aggressively
- Should reduce volume to higher-quality bets

**Expected Impact:**
- Fewer total bets (maybe 10-12 per week vs 15-20)
- Higher win rate on A/B+ grades
- More sustainable long-term

---

### Option 2: Increase Minimum Edge Threshold

**Current:** 3% minimum edge (conservative mode)
**Proposed:** 4% minimum edge

**Rationale:**
- Filter out marginal bets
- Focus on highest-quality opportunities
- Reduce volume but improve quality

**Expected Impact:**
- ~30% fewer bets
- Higher average edge
- Better win rate

---

### Option 3: Disable Adjustments Temporarily

**Revert to base ML model only:**
- No player adjustments
- Pure team stats + form
- See if performance improves

**Rationale:**
- Test if adjustments are the problem
- Baseline comparison
- Can re-enable with better weights

---

### Option 4: Wait and Monitor (Not Recommended)

**Continue with current settings:**
- Track next 20-30 bets
- See if variance evens out

**Risk:**
- Could lose more money
- Might be chasing bad strategy
- Harder to recover confidence

---

## My Recommendation

**Implement Option 1: Cut adjustment weights in half**

### Why:
1. **Preserves the hybrid approach** (which is theoretically sound)
2. **Addresses the overconfidence issue** (most likely cause)
3. **Easy to implement** (one line change)
4. **Reversible** (can adjust again if needed)
5. **Maintains edge detection** (just less aggressive)

### Implementation:
```python
# In ml_model_streamlined.py, _calculate_adjustments()

# Change from:
if home_recent_sv > 0.930:
    adjustments['win_prob_adjustment'] += 0.03  # 3%

# To:
if home_recent_sv > 0.930:
    adjustments['win_prob_adjustment'] += 0.015  # 1.5%

# Apply to all adjustment factors
```

---

## Testing Plan

### Week 1: Reduced Adjustments
- Deploy 50% adjustment weights
- Track all bets
- Monitor A/B+ grade performance

### Week 2: Evaluate
- If win rate improves to 60%+: Keep new weights
- If still struggling: Try Option 2 (higher threshold)
- If variance issue: Increase weights back slightly

### Week 3: Optimize
- Fine-tune weights based on data
- Find sweet spot between volume and accuracy

---

## Statistical Note

**With 19 bets at 47.4% win rate:**
- Expected: ~13 wins (if true rate is 70%)
- Actual: 9 wins
- Difference: -4 wins

**Probability this is just variance:**
- Using binomial distribution
- P(9 or fewer wins | 19 bets, 70% true rate) ≈ 2.3%

**Conclusion:** Only 2.3% chance this is pure variance. Likely a real issue.

---

## Action Items

1. ✅ Identify the problem (done)
2. ⏳ Reduce adjustment weights by 50%
3. ⏳ Deploy and test for 1 week
4. ⏳ Monitor A/B+ grade performance
5. ⏳ Adjust further if needed

---

## Expected Outcome

**After reducing weights:**
- Win rate: 47% → 60-65%
- Volume: 19 bets/week → 12-15 bets/week
- ROI: +1.8% → +25-35%
- A/B+ grades: Back to 60%+ win rate

**Timeline:** Should see improvement within 10-15 bets (3-5 days)

---

## Conclusion

The hybrid model's adjustments are likely **too aggressive**, causing overconfidence in marginal situations. The solution is to **reduce adjustment weights by 50%** and monitor performance.

This is a **real issue, not just variance** (only 2.3% chance of being random), and should be addressed immediately to prevent further losses.

**Next step:** Implement reduced adjustment weights and redeploy.
