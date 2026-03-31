#!/bin/bash
# Daily auto-update script at 4pm
# Runs analysis, builds, and deploys to Firebase

LOG_FILE=~/Desktop/nhllines/cron.log

echo "=== NHL Lines Auto-Update ===" >> "$LOG_FILE"
echo "Started at: $(date)" >> "$LOG_FILE"

# Run the update
cd ~/Desktop/nhllines

# Activate venv and run analysis
source venv/bin/activate
python3 main.py --stake 0.50 --conservative >> "$LOG_FILE" 2>&1

if [ $? -ne 0 ]; then
    echo "❌ Analysis failed - check log for details" >> "$LOG_FILE"
    echo "" >> "$LOG_FILE"
    exit 1
fi

# Copy files (including performance data if available)
cp latest_analysis.json ~/Desktop/projects/public/nhllines/
if [ -f bet_results.json ]; then
    cp bet_results.json ~/Desktop/projects/public/nhllines/
fi
if [ -f analysis_history.json ]; then
    cp analysis_history.json ~/Desktop/projects/public/nhllines/
fi

# Build and deploy
cd ~/Desktop/projects
npm run build >> "$LOG_FILE" 2>&1
cp -r public/nhllines build/
firebase deploy --only hosting >> "$LOG_FILE" 2>&1

if [ $? -eq 0 ]; then
    echo "✅ Deployment successful at $(date)" >> "$LOG_FILE"
else
    echo "❌ Deployment failed" >> "$LOG_FILE"
fi

echo "" >> "$LOG_FILE"
