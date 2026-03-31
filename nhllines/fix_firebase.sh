#!/bin/bash
# Fix Firebase configuration to allow JSON files

echo "Fixing Firebase configuration..."
echo ""

# Backup current firebase.json
cp ~/Desktop/projects/firebase.json ~/Desktop/projects/firebase.json.backup
echo "✅ Backed up firebase.json"

# Create new firebase.json with correct rewrites
cat > ~/Desktop/projects/firebase.json << 'EOF'
{
  "hosting": {
    "public": "build",
    "ignore": [
      "firebase.json",
      "**/.*",
      "**/node_modules/**"
    ]
  }
}
EOF

echo "✅ Updated firebase.json (removed problematic rewrite)"
echo ""
echo "Now deploying to Firebase..."

cd ~/Desktop/projects && firebase deploy --only hosting

echo ""
echo "✅ Done! Test the site at:"
echo "   https://projects-brawlstars.web.app/nhllines/"
echo ""
echo "Test JSON directly at:"
echo "   https://projects-brawlstars.web.app/nhllines/latest_analysis.json"
