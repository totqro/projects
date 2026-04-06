# Quick Start: Model Feedback System

## What Is It?

Your NHL betting model now learns from its predictions and gets better over time. Every bet result teaches the model to make better predictions.

## How to Use It

### Step 1: Run Analysis (As Normal)
```bash
cd nhllines
python main.py
```

The model automatically uses its learned weights. You'll see:
```
[Feedback] Using learned model weight: 0.67
```

### Step 2: Check Bet Results (Daily/Weekly)
```bash
python -m src.analysis.bet_tracker --check --days 7
```

This automatically:
1. Checks which bets won/lost
2. Updates the feedback system
3. Adjusts model weights
4. Shows calibration report

### Step 3: View Learning Progress
```bash
python update_model_feedback.py
```

Shows what the model has learned:
- Win rate vs expected
- Calibration accuracy
- Optimal weights
- Performance by bet type

## That's It!

The model learns automatically. No configuration needed.

## What Gets Better Over Time?

1. **Prediction Accuracy**: Model learns when it's over/underconfident
2. **Model/Market Blend**: Adjusts how much to trust model vs market
3. **Bet Selection**: Filters out historically poor bet types
4. **Confidence Scores**: Recalibrates to match reality

## Example: Before vs After Learning

### Before (Default Weights)
```
Model Weight: 0.65 (fixed)
Confidence: Raw model output
Bets Found: 12
Win Rate: 52% (expected 55%)
```

### After 50 Bets (Learned Weights)
```
Model Weight: 0.71 (learned - model is accurate!)
Confidence: Calibrated (scaled by 1.08)
Bets Found: 10 (filtered out 2 poor performers)
Win Rate: 58% (expected 56%)
```

## Monitoring

Check learning progress anytime:
```bash
# Quick check
python update_model_feedback.py

# Detailed results
python -m src.analysis.bet_tracker --check --days 14
```

## Troubleshooting

**Q: Not seeing any learning?**
- Need at least 20 resolved bets before adjustments kick in
- Run bet tracker to check results first

**Q: Want to reset learning?**
```bash
rm nhllines/data/model_feedback.json
```
Model will start fresh with default weights.

## Advanced: Manual Override

Edit `data/model_feedback.json` to manually set weights:
```json
{
  "optimal_weights": {
    "model_weight": 0.70,
    "confidence_scaling": 0.95
  }
}
```

## More Info

See `docs/MODEL_FEEDBACK.md` for complete documentation.
