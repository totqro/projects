#!/bin/bash
# Setup machine learning dependencies

echo "🤖 Setting up Machine Learning for NHL Lines"
echo "============================================="
echo ""

# Check if Homebrew is installed (for Mac)
if [[ "$OSTYPE" == "darwin"* ]]; then
    if ! command -v brew &> /dev/null; then
        echo "⚠️  Homebrew not found. Install from https://brew.sh"
        echo "Or install libomp manually"
    else
        echo "[0/3] Installing OpenMP (required for XGBoost on Mac)..."
        brew install libomp
    fi
fi

# Activate venv
source venv/bin/activate

# Install ML dependencies
echo ""
echo "[1/3] Installing XGBoost..."
pip install xgboost scikit-learn -q

if [ $? -eq 0 ]; then
    echo "✅ XGBoost installed successfully"
else
    echo "❌ Failed to install XGBoost"
    exit 1
fi

# Train initial model
echo ""
echo "[2/3] Training initial ML model..."
python3 << 'EOF'
from ml_model import NHLMLModel
from nhl_data import fetch_standings, fetch_season_games, get_team_recent_form

print("Fetching training data...")
standings = fetch_standings()
games = fetch_season_games(days_back=90)

print("Calculating team forms...")
team_forms = {}
for team in standings:
    team_forms[team] = get_team_recent_form(team, games, n=10)

print("Training models...")
ml_model = NHLMLModel()
success = ml_model.train(games, standings, team_forms)

if success:
    print("✅ ML models trained and saved!")
else:
    print("❌ Training failed")
EOF

echo ""
echo "============================================="
echo "✅ Machine Learning setup complete!"
echo ""
echo "The ML model will now:"
echo "  • Learn patterns from 90 days of game data"
echo "  • Predict win probabilities using XGBoost"
echo "  • Blend with similarity-based predictions"
echo "  • Retrain automatically with each analysis"
echo ""
echo "Run analysis with ML:"
echo "  python3 main.py --stake 0.50 --conservative"
echo ""
