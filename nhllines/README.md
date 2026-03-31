# NHL +EV Betting Finder

**Status:** Production - Optimized and Validated  
**Performance:** 60% win rate, +33% ROI (35 bets tracked)  
**Deployment:** https://projects-brawlstars.web.app/nhllines/

---

## Quick Start

```bash
# Run daily analysis
python main.py --conservative

# Check bet results
python bet_tracker.py --check

# View system status
python system_report.py
```

---

## Project Structure

```
nhllines/
├── src/                    # Core Python modules
│   ├── main.py            # Main analysis pipeline
│   ├── ml_model_streamlined.py  # Optimized ML model
│   ├── model.py           # Similarity-based model
│   ├── odds_fetcher.py    # Odds API integration
│   ├── nhl_data.py        # NHL API data fetching
│   ├── ev_calculator.py   # EV and edge calculations
│   ├── bet_tracker.py     # Performance tracking
│   ├── goalie_tracker.py  # Goalie data & quality scores
│   ├── injury_tracker.py  # Injury tracking
│   ├── advanced_stats.py  # Advanced metrics
│   └── ...                # Other modules
│
├── docs/                   # Documentation
│   ├── SYSTEM_OVERVIEW.md # Complete system overview
│   ├── BETTING_PRINCIPLES.md  # Core philosophy
│   ├── QUICK_REFERENCE.md # User guide
│   ├── CLV_IMPLEMENTATION_PLAN.md  # Next priority
│   └── ...                # Other guides
│
├── web/                    # Web interface
│   ├── index.html         # Main page
│   ├── styles.css         # Styling
│   └── app.js             # Frontend logic
│
├── scripts/                # Deployment & utility scripts
│   ├── deploy.sh          # Firebase deployment
│   ├── setup_ml.sh        # ML model setup
│   └── ...                # Other scripts
│
├── data/                   # Data files (gitignored)
│   ├── analysis_history.json
│   ├── bet_results.json
│   └── latest_analysis.json
│
├── cache/                  # API cache (gitignored)
├── ml_models/              # Trained models (gitignored)
├── config.json             # API keys (gitignored)
└── README.md               # This file
```

---

## Documentation

### Getting Started
- **[Quick Reference](docs/QUICK_REFERENCE.md)** - How to use the system
- **[System Overview](docs/SYSTEM_OVERVIEW.md)** - Complete system documentation
- **[Integration Guide](docs/INTEGRATION_GUIDE.md)** - Setup instructions

### Core Concepts
- **[Betting Principles](docs/BETTING_PRINCIPLES.md)** - Philosophy and best practices
- **[Implementation Checklist](docs/IMPLEMENTATION_CHECKLIST.md)** - Feature status
- **[CLV Implementation Plan](docs/CLV_IMPLEMENTATION_PLAN.md)** - Next priority

### Analysis & Performance
- **[Optimization Complete](docs/OPTIMIZATION_COMPLETE.md)** - Why we removed manual adjustments
- **[Performance Analysis](docs/PERFORMANCE_ANALYSIS.md)** - Performance deep dive
- **[Model Analysis Findings](docs/MODEL_ANALYSIS_FINDINGS.md)** - Model insights

### Feature Guides
- **[Injury Impact Analysis](docs/INJURY_IMPACT_ANALYSIS.md)** - Historical injury analysis
- **[ML Model Retraining](docs/ML_MODEL_RETRAINING.md)** - Automatic model updates
- **[Goalie Tracker](docs/GOALIE_TRACKER_README.md)** - Goalie tracking system
- **[Injury Tracker](docs/INJURY_TRACKER_README.md)** - Injury impact tracking
- **[Bet Tracking](docs/BET_TRACKING_GUIDE.md)** - Performance tracking
- **[API Key Rotation](docs/API_KEY_ROTATION_GUIDE.md)** - Multi-key setup

---

## Key Features

### ✅ Implemented
- 90-day historical game data
- Real-time odds from multiple bookmakers
- Multi-API key rotation (3 keys, automatic switching)
- **Automatic ML model retraining** (models stay fresh, retrain when > 7 days old)
- **Historical injury impact analysis** (quantified from 799 games, position-specific weighting)
- Starting goalie confirmation + quality scores
- Injury impact tracking with data-driven adjustments
- Advanced stats (Corsi, xGF, PP%, PK%)
- Home/road split analysis
- Back-to-back fatigue detection
- Expected value (EV) calculation
- Bet grading (A, B+, B, C+)
- Performance tracking by grade

### 🔜 High Priority
- Closing Line Value (CLV) tracking
- Line movement tracking
- Enhanced backtesting

---

## Performance

### Current Stats (35 bets)
- **Win Rate:** 60%
- **ROI:** +33%
- **Best Day:** March 6 (5-1, 83.3%)
- **Average Edge:** 5.36%

### By Grade
- **A-grade (7%+ edge):** Limited sample
- **B+ grade (4-7% edge):** Strong performance
- **B grade (3-4% edge):** Solid performance

---

## Configuration

### API Keys
Create `config.json`:
```json
{
    "odds_api_key": "YOUR_KEY_1",
    "odds_api_key_two": "YOUR_KEY_2",
    "odds_api_key_three": "YOUR_KEY_3"
}
```

Get free API keys at: https://the-odds-api.com

### Settings
- **Historical window:** 90 days
- **Similar games:** 50 per analysis
- **ML blend:** 45% ML, 55% similarity
- **Min edge:** 3% (conservative mode)

---

## Usage

### Daily Workflow

1. **Morning Analysis**
   ```bash
   python main.py --conservative
   ```
   Models automatically retrain if > 7 days old (takes ~30 seconds).

2. **Review Recommendations**
   - Check bet grades (focus on A and B+)
   - Review goalie matchups
   - Verify injury reports

3. **Track Results**
   ```bash
   python bet_tracker.py --check
   ```

### Manual Model Retraining

Models retrain automatically, but you can force it anytime:
```bash
python retrain_models.py
```

See `docs/ML_MODEL_RETRAINING.md` for details.

### Command Options

```bash
# Full analysis with live odds
python main.py --conservative

# Historical analysis only (no API key needed)
python main.py --no-odds

# Custom settings
python main.py --stake 0.50 --days 120 --min-edge 0.03

# Check bet results (last 7 days)
python bet_tracker.py --check --days 7
```

---

## Philosophy

### Core Principles

1. **Data quality > Model complexity**
   - Clean data beats fancy algorithms

2. **Market efficiency is real**
   - Don't fight the closing line
   - Player-level factors are priced in

3. **Edge detection > Outcome prediction**
   - Focus on EV, not win probability
   - CLV is the north star metric

4. **Start simple, add complexity**
   - Validate each addition
   - Remove what doesn't work

5. **Bankroll management matters**
   - Kelly criterion for sizing
   - Conservative mode for safety

### Key Lesson

**Manual adjustments hurt performance** (-48% to -62% impact). The market already prices in player-level factors efficiently. Our edge comes from better statistical modeling, not from trying to outsmart the market.

---

## Development

### Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Train ML models
python setup_ml.sh

# Run tests
python -m pytest tests/
```

### Deploy
```bash
# Deploy to Firebase
./scripts/deploy.sh

# Quick deploy (skip build)
./scripts/quick_deploy.sh
```

---

## Support

### Troubleshooting
- Check API quota in output
- Clear cache: `rm -rf cache/*`
- Verify config: `cat config.json`
- Check diagnostics: `python system_report.py`

### Documentation
All documentation is in the `docs/` folder. Start with:
- `docs/QUICK_REFERENCE.md` for usage
- `docs/SYSTEM_OVERVIEW.md` for complete documentation
- `docs/BETTING_PRINCIPLES.md` for philosophy

---

## License

Private project - Not for distribution

---

## Status

**Production Ready** ✅  
**Performance Validated** ✅  
**Auto-Retraining Enabled** ✅  
**Next Priority:** CLV tracking 📊

Last Updated: March 8, 2026
