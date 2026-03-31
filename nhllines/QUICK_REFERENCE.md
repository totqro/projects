# NHL Betting System - Quick Reference

## Daily Usage

### Run Analysis (Conservative Mode)
```bash
python main.py --stake 0.50 --conservative
```
- Moneylines + totals only
- 3%+ edge minimum
- $0.50 stake per bet

### Check Bet Results
```bash
python bet_tracker.py --check --days 7
```
- Updates results for last 7 days
- Shows performance by grade
- Calculates win rate and ROI

### Deploy to Website
```bash
./build_and_deploy.sh
```
- Builds and deploys to Firebase
- Updates both tabs (picks + performance)
- URL: https://projects-brawlstars.web.app/nhllines/

---

## System Monitoring

### Check System Status
```bash
python system_report.py
```
Shows:
- ML model status
- Cache efficiency
- API quota remaining
- Bet tracking stats
- Optimization recommendations

### Optimize Cache
```bash
python optimize_cache.py --optimize
```
- Cleans old cache files (>7 days)
- Shows before/after stats
- Preserves important data

---

## Current Performance

**Tracked Bets:** 4  
**Win Rate:** 100% (4-0)  
**ROI:** +137.3%  
**Profit:** +$2.75 on $2.00 staked

**By Grade:**
- A (7%+ edge): 1 bet, +215% ROI
- B+ (4-7%): 1 bet, +105% ROI  
- B (3-4%): 2 bets, +114.6% ROI

---

## System Status

✅ **ML Models:** 3 trained (1.1 MB)  
✅ **Cache:** 139 files, 1.48 MB, 0 stale  
✅ **API Quota:** 464/500 remaining (92.8%)  
✅ **Optimizations:** All applied

---

## Key Optimizations

1. **ML Hyperparameters:** 150 trees, depth 6, regularization
2. **Feature Count:** 30 (20 base + 10 player)
3. **Blending:** 45% ML + 55% similarity
4. **Model Weight:** 40% model + 60% market
5. **API Efficiency:** 6 calls/day (was 48)
6. **Cache Strategy:** Smart durations per data type
7. **Confidence Scaling:** Square-root for better distribution

---

## Maintenance Schedule

**Daily (Automated):**
- Analysis at 4:00 PM
- Website auto-update

**Weekly (Manual):**
- `python bet_tracker.py --check`
- Review website performance tab

**Monthly (Manual):**
- `python optimize_cache.py --optimize`
- `python system_report.py`

---

## Troubleshooting

**No bets found?**
- Normal on some days
- Conservative mode requires 3%+ edge
- Check confidence levels in output

**API quota low?**
- Check: `cache/quota_info.json`
- Daily updates use ~6 credits
- 500/month = ~16 credits/day budget

**Models not trained?**
- Run: `python main.py --no-odds`
- Trains on historical data
- Takes ~30 seconds

**Website not updating?**
- Run: `./build_and_deploy.sh`
- Check Firebase deployment logs
- Verify files copied to ~/Desktop/projects/public/nhllines/

---

## File Locations

**Analysis Output:** `latest_analysis.json`  
**Bet Results:** `bet_results.json`  
**History:** `analysis_history.json`  
**ML Models:** `ml_models/*.pkl`  
**Cache:** `cache/*.json`  
**Config:** `config.json` (API key)

---

## Important Notes

- **Conservative mode recommended:** Lower risk, higher quality bets
- **Stake $0.50-$1.00 per bet:** Optimal bankroll management
- **Track all bets:** Validates model accuracy over time
- **Review weekly:** Check performance tab on website
- **API quota:** 464 remaining, very healthy

---

## Links

**Website:** https://projects-brawlstars.web.app/nhllines/  
**GitHub:** https://github.com/totqro/nhllines  
**Project Hub:** https://projects-brawlstars.web.app/

---

*Last updated: March 2, 2026*
