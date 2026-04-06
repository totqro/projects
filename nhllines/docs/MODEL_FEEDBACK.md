# Model Feedback System

The NHL betting model now includes a feedback loop that learns from actual bet results to continuously improve predictions.

## How It Works

### 1. Calibration Tracking
The system tracks whether predictions match reality:
- If the model says a bet has 60% win probability, does it actually win 60% of the time?
- Calculates Brier score to measure prediction accuracy
- Groups predictions into probability bins (50-55%, 55-60%, etc.) to identify systematic biases

### 2. Dynamic Weight Adjustment
Based on recent performance, the system automatically adjusts:
- **Model/Market Blend**: If model predictions are accurate, increase model weight (up to 75%). If inaccurate, trust market more (down to 50%)
- **Confidence Scaling**: If model is overconfident, scale down confidence scores. If underconfident, scale up
- **Bet Type Filtering**: Learn which bet types (Moneyline, Total, Spread) perform best

### 3. Context-Specific Learning
The system tracks accuracy for different contexts:
- Back-to-back games
- Goalie matchups
- Injury situations
- Home/road splits
- Confidence levels

### 4. Intelligent Bet Filtering
Uses historical performance to filter out bets that historically underperform:
- If Spread bets have <50% win rate, require higher edge
- If low-confidence bets consistently lose, skip them
- If certain bet types underperform, adjust thresholds

## Usage

### Automatic Updates
The feedback system updates automatically when you check bet results:

```bash
python -m src.analysis.bet_tracker --check --days 7
```

This will:
1. Check which bets won/lost
2. Update bet_results.json
3. Automatically update model feedback
4. Recalculate optimal weights

### Manual Updates
You can also manually update the feedback system:

```bash
python update_model_feedback.py
```

### View Calibration Report
The calibration report shows:
- Overall win rate vs expected
- Calibration by probability bin
- Performance by bet type
- Current optimal weights
- Over/underconfidence indicators

Example output:
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
     65%: 100.0% actual (1/1) [+35.0%]

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

## Data Storage

Feedback data is stored in `nhllines/data/model_feedback.json`:

```json
{
  "calibration_bins": {
    "50": {"correct": 12, "total": 25},
    "55": {"correct": 9, "total": 15}
  },
  "optimal_weights": {
    "model_weight": 0.67,
    "confidence_scaling": 1.05
  },
  "recent_performance": [
    {
      "bet_id": "TOR @ BOS_TOR ML",
      "won": true,
      "true_prob": 0.58,
      "confidence": 0.72,
      "edge": 0.045
    }
  ]
}
```

## Integration with Main Analysis

The feedback system is automatically integrated into `main.py`:

1. **Load learned weights** at startup
2. **Adjust confidence** based on calibration
3. **Blend model/market** using optimal weight
4. **Filter bets** using learned criteria

You don't need to do anything special - just run the analysis as normal:

```bash
python main.py
```

The model will automatically use its learned weights and filters.

## Benefits

1. **Self-Improving**: Model gets better over time as it learns from mistakes
2. **Adaptive**: Automatically adjusts to changing market conditions
3. **Transparent**: Clear reports show what the model is learning
4. **Conservative**: Won't make drastic changes without sufficient data (minimum 20 bets)

## Monitoring

Check the feedback system periodically:

```bash
# Update and view calibration report
python update_model_feedback.py

# Check recent bet results
python -m src.analysis.bet_tracker --check --days 14
```

## Advanced: Manual Weight Override

If you want to temporarily override learned weights, you can edit `data/model_feedback.json`:

```json
{
  "optimal_weights": {
    "model_weight": 0.70,  // Increase to trust model more
    "confidence_scaling": 0.95  // Decrease if model is overconfident
  }
}
```

The system will continue learning and may adjust these values based on new results.

## Troubleshooting

**Q: Model weight isn't changing**
- Need at least 20 resolved bets before adjustments kick in
- Check `data/bet_results.json` has resolved bets

**Q: Calibration report shows "No resolved bets"**
- Run `python -m src.analysis.bet_tracker --check` first
- Make sure games have finished and results are available

**Q: Want to reset learning**
- Delete `data/model_feedback.json`
- System will start fresh with default weights (0.65 model weight)

## Future Enhancements

Potential improvements:
- Context-specific weight adjustments (e.g., trust model more for back-to-back games)
- Time-decay for old results (recent performance weighted more)
- Separate calibration for different bet types
- Bayesian updating for smoother weight adjustments
