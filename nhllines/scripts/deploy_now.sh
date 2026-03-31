#!/bin/bash
# Quick deploy - assumes analysis is already run

echo "🚀 Deploying NHL Lines to Firebase"
echo "==================================="
echo ""

# Copy files
echo "[1/3] Copying files to projects folder..."
cp latest_analysis.json index.html styles.css app.js ~/Desktop/projects/public/nhllines/
echo "✅ Files copied"

# Build
echo ""
echo "[2/3] Building React app..."
cd ~/Desktop/projects
npm run build > /dev/null 2>&1

# Copy nhllines to build
cp -r public/nhllines build/
echo "✅ Build complete"

# Deploy
echo ""
echo "[3/3] Deploying to Firebase..."
firebase deploy --only hosting

echo ""
echo "✅ Deployment complete!"
echo ""
echo "🌐 NHL Lines: https://projects-brawlstars.web.app/nhllines/"
echo "🌐 Project Hub: https://projects-brawlstars.web.app/"
echo ""
echo "Navigation links:"
echo "  ✓ NHL Lines → Project Hub (← Back to Projects button)"
echo "  ✓ Project Hub → NHL Lines (add 'completed' topic to GitHub repo)"
