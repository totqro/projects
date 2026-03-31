# ML Model Retraining Guide

**Last Updated:** March 8, 2026

---

## Current Status

✅ **Models retrained:** March 8, 2026  
✅ **Training data:** 567 games (last 90 days)  
✅ **Models:** Win probability, Total goals, Spread

---

## Why Retraining Matters

The ML models learn patterns from historical games. Over time, they become stale because:

1. **New games aren't included** - Yesterday's games aren't in the training data
2. **Team performance changes** - Injuries, trades, hot/cold streaks
3. **Season progression** - Teams play differently early vs. late season
4. **Goalie changes** - Starting goalies change, affecting team performance

**Recommendation:** Retrain models weekly or when performance drops.

---

## How to Retrain

### Manual Retraining

```bash
# Retrain with latest 90 days of data
python retrain_models.py

# Or specify custom days
python retrain_models.py --days 120
```

This will:
1. Fetch latest standings
2. Fetch last 90 days of games
3. Calculate team form
4. Delete old models
5. Train new models
6. Save to `ml_models/` folder

**Time:** ~30 seconds

---

## When to Retrain

### Recommended Schedule

**Weekly (Recommended):**
```bash
# Every Monday morning
python retrain_models.py
```

**After Major Events:**
- Trade deadline
- Significant injuries to star players
- Long break (All-Star, holidays)

**When Performance Drops:**
- Win rate drops below 55%
- ROI becomes negative
- Model predictions seem off

---

## Automatic Retraining

✅ **IMPLEMENTED:** Models now auto-retrain when > 7 days old!

### How It Works

Every time you run `python main.py`, the system:
1. Checks if models exist
2. Checks their age (last modified date)
3. If > 7 days old, automatically retrains with latest data
4. If fresh, loads from disk

**You don't need to do anything!** Just run your daily analysis and models stay fresh.

### Manual Override

You can still manually retrain anytime:
```bash
python retrain_models.py
```

### Optional: Cron Job

```bash
# Optional: Force retraining every Monday at 6 AM
0 6 * * 1 cd /path/to/nhllines && python retrain_models.py
```

Note: With automatic retraining, this is optional. Models will auto-retrain when needed.

---

## What Gets Updated

### Training Data
- **Before:** Games from 90 days before March 3
- **After:** Games from 90 days before today (March 8)
- **New games added:** ~5 days worth (30-40 games)

### Model Parameters
The models use the same hyperparameters but learn new patterns:
- Win probability patterns
- Scoring trends
- Home/away advantages
- Team matchup dynamics

### What Doesn't Change
- Model architecture (XGBoost)
- Hyperparameters (n_estimators, max_depth, etc.)
- Feature extraction logic
- Similarity model (uses live data, not trained)

---

## Checking Model Performance

### Before Retraining
```bash
# Check current model dates
ls -lh ml_models/*.pkl
```

### After Retraining
```bash
# Run analysis and compare results
python main.py --conservative

# Check if predictions seem more accurate
# Monitor win rate over next 10-20 bets
```

### Validation
- Compare predictions to market odds
- Check if edges are realistic (2-8%)
- Monitor actual bet results

---

## Model Files

Located in `ml_models/` folder:

- **win_model.pkl** - Win probability classifier (~260 KB)
- **total_model.pkl** - Total goals regressor (~415 KB)
- **spread_model.pkl** - Goal differential regressor (~410 KB)

These are XGBoost models trained on:
- Team stats (win %, points %, GF/GA)
- Recent form (last 10 games)
- Home/away splits
- Goal differentials

---

## Troubleshooting

### "Not enough training data"
- Increase `--days` parameter
- Check if NHL API is accessible
- Verify games are being fetched

### Models perform worse after retraining
- May need more data (increase days)
- Check if recent games are outliers
- Consider reverting to previous models (keep backups)

### Import errors
- Make sure you're in the project root
- Virtual environment activated
- All dependencies installed

---

## Best Practices

1. **Keep backups** - Copy old models before retraining
   ```bash
   cp -r ml_models ml_models_backup_$(date +%Y%m%d)
   ```

2. **Monitor performance** - Track win rate after retraining
   ```bash
   python bet_tracker.py --check
   ```

3. **Retrain regularly** - Weekly schedule keeps models fresh

4. **Document changes** - Note when you retrain and why

5. **Compare predictions** - Check if new models make sense

---

## Example Workflow

```bash
# Monday morning routine
cd ~/Desktop/nhllines

# 1. Backup old models
cp -r ml_models ml_models_backup

# 2. Retrain with latest data
python retrain_models.py

# 3. Run analysis
python main.py --conservative

# 4. Deploy to web
bash scripts/quick_deploy.sh

# 5. Monitor performance
python bet_tracker.py --check
```

---

## FAQ

**Q: How often should I retrain?**  
A: Weekly is good. More often if performance drops.

**Q: Will retraining improve accuracy?**  
A: Usually yes, especially if models are > 2 weeks old.

**Q: Can I retrain with more/less data?**  
A: Yes, use `--days` parameter. 90 days is optimal.

**Q: What if retraining makes it worse?**  
A: Restore from backup and investigate why.

**Q: Does retraining cost API calls?**  
A: Yes, ~1-2 calls to fetch game data.

---

## Current Model Info

**Last Retrained:** March 8, 2026  
**Training Games:** 567  
**Date Range:** Dec 9, 2025 - Mar 8, 2026  
**Performance:** 60% win rate, +33% ROI

---

**Next Recommended Retraining:** March 15, 2026 (weekly schedule)
