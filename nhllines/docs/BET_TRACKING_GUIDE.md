# Bet Tracking Guide

The NHL Lines system now automatically tracks all recommended bets and can check their results to show your actual performance.

## How It Works

1. **Automatic Logging**: Every time you run `main.py`, the top recommended bets are automatically logged to `bet_history.json`

2. **Result Checking**: Run the bet tracker to check results of past bets once games are completed

3. **Performance Stats**: See your actual win rate, ROI, and profit/loss

## Usage

### Check Past Bet Results

After games have been played, check the results:

```bash
python bet_tracker.py --check --days 7
```

This will:
- Fetch game results from the last 7 days
- Match them against your logged bets
- Calculate wins/losses and profit
- Show performance summary

### View Performance in Main Analysis

When you run the main analysis, if you have tracked bet history, it will show at the bottom:

```bash
python main.py --stake 0.50 --conservative
```

Output includes:
```
PAST PERFORMANCE (Tracked Bets)
Total bets: 45 | Won: 24 (53.3%) | Lost: 21
Total staked: $22.50 | Profit: +$3.45 | ROI: +15.3%
```

## What Gets Tracked

For each bet, the system logs:
- Date and timestamp
- Game matchup
- Pick (e.g., "TOR ML", "Over 6.5")
- Bet type (Moneyline, Total, Spread)
- Odds and stake
- Model edge and expected value
- Confidence level
- **Result** (filled in later when you run --check)
- **Profit/Loss** (calculated after result)

## Example Workflow

### Day 1 (Sunday):
```bash
# Run analysis, bets are automatically logged
python main.py --stake 0.50 --conservative

# Output shows:
# ✅ Logged 7 bets to bet_history.json
```

### Day 2 (Monday):
```bash
# Check results from yesterday's games
python bet_tracker.py --check --days 2

# Output shows:
# ✅ Updated 7 bet results
# 
# BET PERFORMANCE SUMMARY
# Total bets tracked: 7
# Won: 4 (57.1%)
# Lost: 3 (42.9%)
# Total staked: $3.50
# Total profit: $1.23
# ROI: +35.1%
```

### Ongoing:
```bash
# Run analysis daily - performance stats show automatically
python main.py --stake 0.50 --conservative

# Check results weekly
python bet_tracker.py --check --days 7
```

## Performance Metrics

The system calculates:

- **Win Rate**: Percentage of bets that won
- **Total Staked**: Sum of all bet amounts
- **Total Profit**: Net profit/loss across all bets
- **ROI**: Return on investment (profit / staked)

## Tips

1. **Check results regularly**: Run `--check` after game days to keep your stats updated

2. **Compare to model predictions**: The system shows your actual ROI vs the model's predicted ROI

3. **Track over time**: The longer you track, the more accurate your performance stats become

4. **Adjust stake sizes**: If actual ROI is much lower than predicted, consider reducing stake or being more selective

## File Location

All bet history is stored in:
```
~/Desktop/nhllines/bet_history.json
```

This file is automatically created and updated. Don't delete it unless you want to reset your tracking history.

## Limitations

- Only tracks bets from when you started using this feature
- Requires games to be completed before results can be checked
- Spread bets are not fully implemented yet (only ML and totals)
- Results are based on final scores (doesn't account for pushes or overtime rules)

## Future Enhancements

Potential additions:
- Web dashboard showing performance charts
- Email/notification when results are available
- Comparison of different betting strategies
- Bankroll management recommendations based on actual performance
- Export to CSV for external analysis
