#!/bin/bash
# Quick deploy script - run this from nhllines folder

echo "🏒 NHL Lines - Quick Deploy"
echo "============================"
echo ""

# Copy latest analysis
echo "Copying latest_analysis.json to build directory..."
cp data/latest_analysis.json ~/Desktop/projects/build/nhllines/
echo "Copying latest_analysis.json to public directory..."
cp data/latest_analysis.json ~/Desktop/projects/public/nhllines/

echo "✅ Files updated in both build/ and public/"
echo ""
echo "Now deploying to Firebase..."
echo ""

# Deploy from projects directory
cd ~/Desktop/projects && firebase deploy --only hosting
