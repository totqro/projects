# Migration Guide - Updated File Structure

**For users of the old file structure**

---

## What Changed?

The project has been reorganized into a cleaner, more professional structure. **All functionality remains the same** - just the file locations have changed.

---

## Quick Reference

### Running the System

**✅ Still works the same way:**
```bash
python main.py --conservative
```

**Nothing changed here!** The main entry point is still `main.py` in the root directory.

---

## If You're Importing Modules

### Old Way (No longer works)
```python
from nhl_data import fetch_standings
from odds_fetcher import fetch_nhl_odds
from ml_model_streamlined import StreamlinedNHLMLModel
from ev_calculator import calculate_ev
from bet_tracker import get_performance_stats
```

### New Way (Use this)
```python
from src.data import fetch_standings, fetch_nhl_odds
from src.models import StreamlinedNHLMLModel
from src.analysis import calculate_ev, get_performance_stats
```

---

## File Locations

### Python Modules

| Old Location | New Location |
|--------------|--------------|
| `nhl_data.py` | `src/data/nhl_data.py` |
| `odds_fetcher.py` | `src/data/odds_fetcher.py` |
| `scraper.py` | `src/data/scraper.py` |
| `ml_model_streamlined.py` | `src/models/ml_model_streamlined.py` |
| `model.py` | `src/models/model.py` |
| `ev_calculator.py` | `src/analysis/ev_calculator.py` |
| `bet_tracker.py` | `src/analysis/bet_tracker.py` |
| `goalie_tracker.py` | `src/analysis/goalie_tracker.py` |
| `injury_tracker.py` | `src/analysis/injury_tracker.py` |
| `advanced_stats.py` | `src/analysis/advanced_stats.py` |
| `team_splits.py` | `src/analysis/team_splits.py` |
| `backtest_model.py` | `src/utils/backtest_model.py` |

### Documentation

| Old Location | New Location |
|--------------|--------------|
| `BETTING_PRINCIPLES.md` | `docs/BETTING_PRINCIPLES.md` |
| `SYSTEM_OVERVIEW.md` | `docs/SYSTEM_OVERVIEW.md` |
| `QUICK_REFERENCE.md` | `docs/QUICK_REFERENCE.md` |
| All other .md files | `docs/` folder |

### Web Files

| Old Location | New Location |
|--------------|--------------|
| `index.html` | `web/index.html` |
| `styles.css` | `web/styles.css` |
| `app.js` | `web/app.js` |

### Scripts

| Old Location | New Location |
|--------------|--------------|
| `deploy.sh` | `scripts/deploy.sh` |
| `setup_ml.sh` | `scripts/setup_ml.sh` |
| All other .sh files | `scripts/` folder |

### Data Files

| Old Location | New Location |
|--------------|--------------|
| `analysis_history.json` | `data/analysis_history.json` |
| `bet_results.json` | `data/bet_results.json` |
| `latest_analysis.json` | `data/latest_analysis.json` |

---

## What Stayed the Same

✅ **Root directory files:**
- `main.py` - Still the entry point
- `config.json` - Still in root
- `cache/` - Still in root
- `ml_models/` - Still in root

✅ **Command-line interface:**
```bash
python main.py --conservative
python main.py --no-odds
python main.py --stake 0.50
```

✅ **Configuration format:**
```json
{
    "odds_api_key": "YOUR_KEY",
    "odds_api_key_two": "YOUR_KEY_2",
    "odds_api_key_three": "YOUR_KEY_3"
}
```

✅ **All functionality:**
- Same features
- Same performance
- Same output
- Same behavior

---

## Running Modules Directly

### Old Way
```bash
python bet_tracker.py --check
python goalie_tracker.py
python backtest_model.py
```

### New Way (Option 1 - Recommended)
```bash
python -m src.analysis.bet_tracker --check
python -m src.analysis.goalie_tracker
python -m src.utils.backtest_model
```

### New Way (Option 2 - Still works!)
```bash
# Create symlinks in root (one-time setup)
ln -s src/analysis/bet_tracker.py bet_tracker.py
ln -s src/analysis/goalie_tracker.py goalie_tracker.py

# Then use old commands
python bet_tracker.py --check
python goalie_tracker.py
```

---

## If You Have Custom Scripts

### Update Your Imports

**Before:**
```python
#!/usr/bin/env python3
from nhl_data import fetch_standings
from odds_fetcher import fetch_nhl_odds
from ml_model_streamlined import StreamlinedNHLMLModel

# Your code here
```

**After:**
```python
#!/usr/bin/env python3
from src.data import fetch_standings, fetch_nhl_odds
from src.models import StreamlinedNHLMLModel

# Your code here (no other changes needed)
```

---

## Benefits of New Structure

### 1. Cleaner Root Directory
- Only 5 files instead of 50+
- Easy to see what's important
- Professional appearance

### 2. Logical Organization
- Related files grouped together
- Clear separation of concerns
- Easy to find what you need

### 3. Better for Collaboration
- Industry-standard structure
- Easy for others to understand
- Clear where new code belongs

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'nhl_data'"

**Problem:** Using old import style  
**Solution:** Update imports to use `src.` prefix

```python
# Old (doesn't work)
from nhl_data import fetch_standings

# New (works)
from src.data import fetch_standings
```

### "FileNotFoundError: [Errno 2] No such file or directory: 'bet_results.json'"

**Problem:** File moved to `data/` folder  
**Solution:** This should be automatic. If you see this error, the path updates may not have applied. Check that you're using the latest version of the files.

### "Cannot find module 'bet_tracker'"

**Problem:** Trying to run module directly  
**Solution:** Use `python -m` syntax

```bash
# Old (doesn't work)
python bet_tracker.py --check

# New (works)
python -m src.analysis.bet_tracker --check
```

---

## Need Help?

### Check Documentation
- `README.md` - Project overview
- `docs/PROJECT_STRUCTURE.md` - Detailed structure guide
- `docs/QUICK_REFERENCE.md` - User guide
- `REFACTORING_COMPLETE.md` - What changed

### Test Your Setup
```bash
# Test imports
python -c "from src.data import fetch_standings; print('OK')"
python -c "from src.models import StreamlinedNHLMLModel; print('OK')"
python -c "from src.analysis import get_performance_stats; print('OK')"

# Test main script
python main.py --no-odds
```

---

## Summary

**What you need to do:**
1. ✅ Update imports in custom scripts (if any)
2. ✅ Use new module paths when running directly
3. ✅ Check documentation in `docs/` folder

**What you DON'T need to do:**
- ❌ Change how you run `main.py`
- ❌ Change `config.json` format
- ❌ Reinstall dependencies
- ❌ Retrain models
- ❌ Change any configuration

**The system works exactly the same, just better organized!**

---

**Questions?** Check `docs/PROJECT_STRUCTURE.md` for complete details.
