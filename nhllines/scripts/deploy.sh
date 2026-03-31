#!/bin/bash
# Deploy NHL Betting Analysis to Web

echo "NHL +EV Betting Finder - Web Deployment"
echo "========================================"
echo ""

# Step 1: Run the analysis
echo "[1/3] Running analysis..."
python3 main.py --stake 0.50 --conservative

if [ $? -ne 0 ]; then
    echo "Error: Analysis failed. Check your API key and internet connection."
    exit 1
fi

# Step 2: Copy web files to a deploy directory
echo ""
echo "[2/3] Preparing web files..."
mkdir -p web_deploy
cp web/index.html web_deploy/
cp web/styles.css web_deploy/
cp web/app.js web_deploy/
cp data/latest_analysis.json web_deploy/

echo "Web files ready in ./web_deploy/"

# Step 3: Instructions for Firebase
echo ""
echo "[3/3] Next steps for Firebase deployment:"
echo ""
echo "1. Install Firebase CLI (if not already installed):"
echo "   npm install -g firebase-tools"
echo ""
echo "2. Login to Firebase:"
echo "   firebase login"
echo ""
echo "3. Initialize Firebase in the web_deploy folder:"
echo "   cd web_deploy"
echo "   firebase init hosting"
echo "   - Select your Firebase project"
echo "   - Set public directory to: . (current directory)"
echo "   - Configure as single-page app: No"
echo "   - Don't overwrite index.html"
echo ""
echo "4. Deploy to Firebase:"
echo "   firebase deploy"
echo ""
echo "Or test locally first:"
echo "   cd web_deploy"
echo "   python3 -m http.server 8000"
echo "   Then open: http://localhost:8000"
echo ""
