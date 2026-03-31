#!/bin/bash
# Update NHL betting analysis and deploy to Firebase

echo "🏒 NHL Lines - Update & Deploy"
echo "================================"
echo ""

# Step 1: Run analysis
echo "[1/4] Running betting analysis..."
cd ~/Desktop/nhllines
python3 main.py --stake 0.50 --conservative

if [ $? -ne 0 ]; then
    echo "❌ Error: Analysis failed"
    exit 1
fi

# Step 2: Copy to projects folder
echo ""
echo "[2/4] Copying to projects folder..."
cp latest_analysis.json ~/Desktop/projects/public/nhllines/
echo "✅ Files updated"

# Step 3: Build React app
echo ""
echo "[3/4] Building React app..."
cd ~/Desktop/projects
npm run build

if [ $? -ne 0 ]; then
    echo "❌ Error: Build failed"
    exit 1
fi

# Step 4: Deploy to Firebase
echo ""
echo "[4/4] Deploying to Firebase..."
firebase deploy --only hosting

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Deployment complete!"
    echo "🌐 Your site is live at: https://projects-brawlstars.web.app/nhllines/"
else
    echo "❌ Error: Deployment failed"
    exit 1
fi
