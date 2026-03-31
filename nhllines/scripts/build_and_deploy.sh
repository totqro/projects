#!/bin/bash
# Complete build and deploy script for NHL Lines

echo "🏒 NHL Lines - Build & Deploy to Firebase"
echo "=========================================="
echo ""

# Step 1: Update analysis
echo "[1/5] Running betting analysis..."
source venv/bin/activate
python3 main.py --stake 0.50 --conservative

if [ $? -ne 0 ]; then
    echo "❌ Error: Analysis failed"
    exit 1
fi

# Step 2: Copy to projects public folder
echo ""
echo "[2/5] Copying to projects/public/nhllines..."
cp latest_analysis.json ~/Desktop/projects/public/nhllines/
cp index.html ~/Desktop/projects/public/nhllines/
cp styles.css ~/Desktop/projects/public/nhllines/
cp app.js ~/Desktop/projects/public/nhllines/
# Copy performance data if it exists
if [ -f bet_results.json ]; then
    cp bet_results.json ~/Desktop/projects/public/nhllines/
fi
if [ -f analysis_history.json ]; then
    cp analysis_history.json ~/Desktop/projects/public/nhllines/
fi

# Step 3: Build React app
echo ""
echo "[3/5] Building React app..."
cd ~/Desktop/projects
npm run build

if [ $? -ne 0 ]; then
    echo "❌ Error: Build failed"
    exit 1
fi

# Step 4: Copy nhllines to build folder
echo ""
echo "[4/5] Copying nhllines to build folder..."
cp -r public/nhllines build/
echo "✅ nhllines copied to build/"

# Step 5: Deploy to Firebase
echo ""
echo "[5/5] Deploying to Firebase..."
firebase deploy --only hosting

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Deployment complete!"
    echo "🌐 NHL Lines: https://projects-brawlstars.web.app/nhllines/"
    echo "🌐 Project Hub: https://projects-brawlstars.web.app/"
else
    echo "❌ Error: Deployment failed"
    exit 1
fi
