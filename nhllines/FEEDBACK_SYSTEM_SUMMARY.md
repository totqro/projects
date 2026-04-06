# Model Feedback System - Implementation Summary

## What Was Added

A complete machine learning feedback loop that allows the NHL betting model to learn from its predictions and continuously improve over time.

## Key Components

### 1. Model Feedback Module (`src/analysis/model_feedback.py`)
- Tracks prediction accuracy across different probability bins
- Calculates calibration metrics (Brier score, calibration error)
- Dynamically adjusts model/market blend weights
- Recalibrates confidence scores based on historical performance
- Filters bets using learned criteria

### 2. Integration Points

**Bet Tracker** (`src/analysis/bet_tracker.py`)
- Automatically updates feedback system when checking bet results
- Triggers learning after each result check

**Main Analysis** (`main.py`)
- Loads learned optimal weights at startup
- Adjusts confidence scores based on calibration
- Uses dynamic model/market blend
- Filters bets using historical performance data

**GitHub Workflow** (`.github/workflows/daily-nhl-analysis.yml`)
- Automatically updates feedback after checking results
- Commits model_feedback.json to track learning over time

### 3. Utilities

**Manual Update Script** (`update_model_feedback.py`)
- Standalone script to update feedback system
- Shows detailed calibration report

**Test Script** (`test_feedback.py`)
- Tests feedback system with sample data
- Validates all functionality

## How It Works

### Learning Process

1. **Bet Results Come In**
   ```
   Bet: TOR ML @ +150, predicted 55% win prob
   Result: Won
   ```

2. **Calibration Tracking**
   - Groups prediction into 55% probability bin
   - Tracks: "55% predictions won 60% of the time"
   - Identifies if model is over/underconfident

3. **Weight Adjustment**
   - If Brier score < 0.20: Increase model weight (trust model more)
   - If Brier score > 0.25: Decrease model weight (trust market more)
   - Adjusts in small increments (±0.02) for stability

4. **Confidence Recalibration**
   - If model is overconfident: Scale down confidence scores
   - If model is underconfident: Scale up confidence scores
   - Keeps predictions well-calibrated

5. **Bet Filtering**
   - Learns which bet types perform best
   - Filters out historically poor performers
   - Requires higher edge for underperforming categories

### Data Flow

```
Bet Results (bet_results.json)
    ↓
Model Feedback System
    ↓
Calibration Analysis
    ↓
Weight Optimization
    ↓
Updated Weights (model_feedback.json)
    ↓
Future Predictions (main.py)
```

## Usage

### Automatic (Recommended)
The system updates automatically when you check bet results:

```bash
# Check results and update feedback
python -m src.analysis.bet_tracker --check --days 7
```

### Manual
Update feedback system independently:

```bash
# Update and view calibration report
python update_model_feedback.py
```

### Testing
Test the system with sample data:

```bash
python test_feedback.py
```

## What Gets Learned

### 1. Optimal Model Weight
- Starts at 0.65 (65% model, 35% market)
- Adjusts between 0.50 and 0.75 based on performance
- Higher weight = model predictions are more accurate than market

### 2. Confidence Scaling
- Starts at 1.0 (no adjustment)
- Adjusts between 0.7 and 1.3
- <1.0 = model is overconfident, scale down
- >1.0 = model is underconfident, scale up

### 3. Bet Type Performance
- Tracks win rate for Moneyline, Total, Spread
- Requires higher edge for underperforming types
- May skip certain bet types entirely if consistently poor

### 4. Confidence Level Performance
- Tracks accuracy at different confidence levels
- Filters out low-confidence bets if they historically lose
- Identifies "sweet spot" confidence ranges

## Benefits

1. **Self-Improving**: Gets better with every bet result
2. **Adaptive**: Responds to changing market conditions
3. **Conservative**: Requires 20+ bets before making adjustments
4. **Transparent**: Clear reports show what's being learned
5. **Automatic**: No manual intervention needed

## Monitoring

### View Current State
```bash
python update_model_feedback.py
```

Shows:
- Recent win rate vs expected
- Calibration by probability bin
- Performance by bet type
- Current optimal weights
- Over/underconfidence indicators

### Check Data Files
- `nhllines/data/model_feedback.json` - Learned weights and calibration data
- `nhllines/data/bet_results.json` - Historical bet results
- `nhllines/data/analysis_history.json` - All past predictions

## Example Output

```
============================================================
  MODEL CALIBRATION REPORT
============================================================

  Recent Performance (last 45 bets):
    Win Rate: 57.8% (26W-19L)
    Expected: 55.2%
    Difference: +2.6%

  Calibration by Predicted Probability:
  --------------------------------------------------------
     50%: 48.0% actual (12/25) [-2.0%]
     55%: 60.0% actual (9/15) [+5.0%]
     60%: 66.7% actual (4/6) [+6.7%]

  Performance by Bet Type:
  --------------------------------------------------------
    Moneyline   : 62.5% (15/24)
    Total       : 52.4% (11/21)

  Optimal Weights:
  --------------------------------------------------------
    Model Weight: 0.67
    Confidence Scaling: 1.05
    ✅ Model is well-calibrated (+0.3%)
============================================================
```

## Technical Details

### Calibration Metrics

**Brier Score**: Measures prediction accuracy
- Formula: avg((predicted_prob - actual_outcome)²)
- Range: 0.0 (perfect) to 1.0 (worst)
- Good: < 0.20, Poor: > 0.25

**Calibration Error**: Difference between predicted and actual win rates
- Positive = overconfident
- Negative = underconfident
- Well-calibrated: ±5%

### Weight Adjustment Algorithm

```python
if brier_score < 0.20:
    model_weight = min(0.75, current_weight + 0.02)
elif brier_score > 0.25:
    model_weight = max(0.50, current_weight - 0.02)

if calibration_error > 0.05:  # Overconfident
    confidence_scaling = max(0.7, current_scaling - 0.05)
elif calibration_error < -0.05:  # Underconfident
    confidence_scaling = min(1.3, current_scaling + 0.05)
```

### Bet Filtering Logic

```python
# Require higher edge for underperforming bet types
if bet_type_win_rate < 0.50:
    edge_threshold = 0.04  # 4%+
else:
    edge_threshold = 0.02  # 2%+

# Skip low-confidence bets if they historically lose
if confidence < 0.60 and conf_win_rate < 0.45:
    skip_bet = True
```

## Future Enhancements

Potential improvements:
- Context-specific weights (e.g., different weights for B2B games)
- Time-decay for old results (recent performance weighted more)
- Bayesian updating for smoother adjustments
- Separate calibration per bet type
- Ensemble learning with multiple models

## Files Modified

1. `nhllines/src/analysis/model_feedback.py` - New feedback system
2. `nhllines/src/analysis/bet_tracker.py` - Auto-update integration
3. `nhllines/src/analysis/__init__.py` - Export feedback functions
4. `nhllines/main.py` - Use learned weights and filters
5. `nhllines/.gitignore` - Track model_feedback.json
6. `.github/workflows/daily-nhl-analysis.yml` - Auto-update in CI/CD
7. `nhllines/update_model_feedback.py` - Manual update script
8. `nhllines/test_feedback.py` - Test suite
9. `nhllines/docs/MODEL_FEEDBACK.md` - Documentation

## Testing

Run the test suite to verify everything works:

```bash
cd nhllines
python test_feedback.py
```

Expected output:
```
============================================================
  Testing Model Feedback System
============================================================

Testing with 5 sample bets...

✅ Optimal model weight: 0.65
✅ Confidence adjustments:
   0.50 -> 0.50
   0.65 -> 0.65
   0.80 -> 0.80
   0.95 -> 0.95
✅ Bet filtering:
   ✓ TAKE: Moneyline edge=4.0% conf=65%
   ✓ TAKE: Total edge=2.0% conf=50%
   ✓ TAKE: Moneyline edge=6.0% conf=75%

============================================================
  Test Complete!
============================================================
```

## Conclusion

The model now has a complete feedback loop that learns from every bet result. It will automatically:
- Adjust its confidence in predictions
- Optimize the model/market blend
- Filter out poor-performing bet types
- Improve calibration over time

No manual intervention needed - just run the analysis as normal and the model will continuously improve!
