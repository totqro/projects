# Project Structure

**Last Updated:** March 7, 2026

This document describes the organized file structure of the NHL +EV Betting Finder project.

---

## Directory Layout

```
nhllines/
│
├── main.py                 # Main entry point - run analysis here
├── config.json             # API keys configuration (gitignored)
├── requirements.txt        # Python dependencies
├── README.md               # Project overview
│
├── src/                    # Source code
│   ├── __init__.py
│   │
│   ├── models/             # ML and prediction models
│   │   ├── __init__.py
│   │   ├── ml_model.py              # Base ML model
│   │   ├── ml_model_streamlined.py  # Optimized ML model (current)
│   │   ├── ml_model_enhanced.py     # Enhanced ML model (experimental)
│   │   └── model.py                 # Similarity-based model
│   │
│   ├── data/               # Data fetching modules
│   │   ├── __init__.py
│   │   ├── nhl_data.py              # NHL API integration
│   │   ├── odds_fetcher.py          # Odds API + multi-key rotation
│   │   ├── scraper.py               # Web scraping utilities
│   │   └── player_data.py           # Player-specific data
│   │
│   ├── analysis/           # Analysis and tracking modules
│   │   ├── __init__.py
│   │   ├── ev_calculator.py         # EV and edge calculations
│   │   ├── bet_tracker.py           # Performance tracking
│   │   ├── analysis_history.py      # Historical analysis storage
│   │   ├── goalie_tracker.py        # Goalie data & quality scores
│   │   ├── injury_tracker.py        # Injury tracking & impact
│   │   ├── advanced_stats.py        # Advanced metrics (Corsi, xGF)
│   │   └── team_splits.py           # Home/road split analysis
│   │
│   └── utils/              # Utility scripts
│       ├── __init__.py
│       ├── backtest_model.py        # Backtesting framework
│       ├── optimize_adjustments.py  # Optimization analysis
│       ├── optimize_cache.py        # Cache optimization
│       ├── system_report.py         # System diagnostics
│       └── setup.py                 # Setup utilities
│
├── docs/                   # Documentation
│   ├── PROJECT_STRUCTURE.md         # This file
│   ├── SYSTEM_OVERVIEW.md           # Complete system overview
│   ├── BETTING_PRINCIPLES.md        # Core philosophy
│   ├── QUICK_REFERENCE.md           # User guide
│   ├── IMPLEMENTATION_CHECKLIST.md  # Feature status
│   ├── CLV_IMPLEMENTATION_PLAN.md   # Next priority
│   ├── OPTIMIZATION_COMPLETE.md     # Optimization findings
│   ├── PERFORMANCE_ANALYSIS.md      # Performance deep dive
│   ├── MODEL_ANALYSIS_FINDINGS.md   # Model insights
│   ├── GOALIE_TRACKER_README.md     # Goalie tracking guide
│   ├── INJURY_TRACKER_README.md     # Injury tracking guide
│   ├── BET_TRACKING_GUIDE.md        # Performance tracking guide
│   ├── API_KEY_ROTATION_GUIDE.md    # Multi-key setup
│   └── ...                          # Other guides
│
├── web/                    # Web interface
│   ├── index.html          # Main page
│   ├── styles.css          # Styling
│   └── app.js              # Frontend logic
│
├── scripts/                # Deployment & utility scripts
│   ├── deploy.sh           # Firebase deployment
│   ├── quick_deploy.sh     # Quick deploy (skip build)
│   ├── setup_ml.sh         # ML model setup
│   ├── build_and_deploy.sh # Build and deploy
│   └── ...                 # Other scripts
│
├── data/                   # Data files (gitignored)
│   ├── analysis_history.json        # Historical analyses
│   ├── bet_results.json             # Bet tracking results
│   ├── bet_history.json             # Bet history
│   └── latest_analysis.json         # Most recent analysis
│
├── cache/                  # API cache (gitignored)
│   ├── standings_*.json
│   ├── games_*.json
│   ├── odds_*.json
│   ├── goalie_*.json
│   └── ...
│
├── ml_models/              # Trained models (gitignored)
│   ├── nhl_ml_win.pkl
│   ├── nhl_ml_total.pkl
│   └── nhl_ml_spread.pkl
│
├── tests/                  # Test files (future)
│
├── .venv/                  # Virtual environment (gitignored)
├── .git/                   # Git repository
├── .gitignore              # Git ignore rules
└── .vscode/                # VS Code settings (gitignored)
```

---

## Module Organization

### Core Modules (src/)

#### models/
Contains all prediction models:
- **ml_model_streamlined.py** - Current production model (pure ML, no adjustments)
- **model.py** - Similarity-based predictions
- **ml_model.py** - Base ML model class
- **ml_model_enhanced.py** - Experimental enhanced model

#### data/
Handles all external data fetching:
- **nhl_data.py** - NHL API (games, standings, stats)
- **odds_fetcher.py** - The Odds API (betting lines, multi-key rotation)
- **scraper.py** - Web scraping (player data, schedules)
- **player_data.py** - Player-specific data fetching

#### analysis/
Analysis and tracking functionality:
- **ev_calculator.py** - Expected value calculations
- **bet_tracker.py** - Performance tracking and reporting
- **analysis_history.py** - Historical analysis storage
- **goalie_tracker.py** - Goalie confirmations and quality scores
- **injury_tracker.py** - Injury reports and impact calculations
- **advanced_stats.py** - Advanced metrics (Corsi, xGF, PP%, PK%)
- **team_splits.py** - Home/road performance analysis

#### utils/
Utility scripts and tools:
- **backtest_model.py** - Backtesting framework
- **optimize_adjustments.py** - Optimization analysis
- **optimize_cache.py** - Cache management
- **system_report.py** - System diagnostics

---

## Import Structure

### From Main Script
```python
# Import from organized modules
from src.data import fetch_standings, fetch_nhl_odds
from src.models import StreamlinedNHLMLModel, find_similar_games
from src.analysis import evaluate_all_bets, get_performance_stats
```

### Within src/ Modules
```python
# Relative imports within same package
from .ml_model import NHLMLModel

# Absolute imports from other packages
from src.data.nhl_data import fetch_standings
from src.analysis.ev_calculator import calculate_ev
```

---

## File Paths

### Configuration
- **config.json** - Root directory (gitignored)
- **requirements.txt** - Root directory

### Data Storage
- **data/** - All JSON data files
  - analysis_history.json
  - bet_results.json
  - latest_analysis.json

### Cache
- **cache/** - All API cache files
  - Automatically created by modules
  - Organized by data type

### Models
- **ml_models/** - Trained ML models
  - Automatically created during training
  - Persisted between runs

---

## Running the System

### From Root Directory
```bash
# Main analysis
python main.py --conservative

# Bet tracking
python -m src.analysis.bet_tracker --check

# System report
python -m src.utils.system_report

# Backtesting
python -m src.utils.backtest_model
```

### Module Testing
```bash
# Test goalie tracker
python -m src.analysis.goalie_tracker

# Test injury tracker
python -m src.analysis.injury_tracker

# Test odds fetcher
python -m src.data.odds_fetcher
```

---

## Benefits of This Structure

### 1. Clear Separation of Concerns
- **models/** - Prediction logic
- **data/** - Data fetching
- **analysis/** - Analysis and tracking
- **utils/** - Utilities and tools

### 2. Easy to Navigate
- Related files grouped together
- Clear naming conventions
- Logical hierarchy

### 3. Scalable
- Easy to add new modules
- Clear where new code belongs
- Modular design

### 4. Maintainable
- Isolated changes
- Clear dependencies
- Easy to test

### 5. Professional
- Industry-standard structure
- Easy for others to understand
- Ready for collaboration

---

## Migration Notes

### What Changed
1. **Python files** moved to `src/` with subfolders
2. **Documentation** moved to `docs/`
3. **Web files** moved to `web/`
4. **Scripts** moved to `scripts/`
5. **Data files** moved to `data/`
6. **Imports** updated to use `src.` prefix
7. **File paths** updated to reference correct locations

### What Stayed the Same
1. **main.py** - Still in root (entry point)
2. **config.json** - Still in root (configuration)
3. **cache/** - Still in root (shared cache)
4. **ml_models/** - Still in root (shared models)

### Backward Compatibility
- All functionality preserved
- No breaking changes to API
- Same command-line interface
- Same configuration format

---

## Adding New Features

### New Data Source
1. Create file in `src/data/`
2. Add to `src/data/__init__.py`
3. Import in main.py or other modules

### New Model
1. Create file in `src/models/`
2. Inherit from base classes if applicable
3. Add to `src/models/__init__.py`

### New Analysis Module
1. Create file in `src/analysis/`
2. Add to `src/analysis/__init__.py`
3. Import where needed

### New Utility
1. Create file in `src/utils/`
2. Make it runnable with `python -m src.utils.module_name`

---

## Best Practices

### Imports
- Use absolute imports from `src.`
- Use relative imports within same package
- Keep imports organized (stdlib, third-party, local)

### File Paths
- Use `Path(__file__).parent` for relative paths
- Reference root with `.parent.parent` as needed
- Store data in `data/`, cache in `cache/`

### Documentation
- Keep docs in `docs/` folder
- Update PROJECT_STRUCTURE.md when adding folders
- Document new modules in their docstrings

### Testing
- Add tests to `tests/` folder
- Mirror src/ structure in tests/
- Use `pytest` for test runner

---

## Quick Reference

### Common Paths
```python
from pathlib import Path

# Root directory
ROOT = Path(__file__).parent

# Data directory
DATA_DIR = ROOT / "data"

# Cache directory
CACHE_DIR = ROOT / "cache"

# ML models directory
MODELS_DIR = ROOT / "ml_models"

# Config file
CONFIG_PATH = ROOT / "config.json"
```

### Common Imports
```python
# Data fetching
from src.data import fetch_standings, fetch_nhl_odds

# Models
from src.models import StreamlinedNHLMLModel, find_similar_games

# Analysis
from src.analysis import evaluate_all_bets, get_performance_stats

# Utilities
from src.utils.backtest_model import backtest_model
```

---

**Status:** Organized and validated ✅  
**All imports:** Working correctly ✅  
**All paths:** Updated and tested ✅
