#!/bin/bash
# NHL +EV Betting Finder - launcher script
# Handles virtual environment setup automatically

cd "$(dirname "$0")"

# Create venv if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Setting up virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install requests -q
    echo "Setup complete!"
else
    source venv/bin/activate
fi

# Pass all arguments through to main.py
python main.py "$@"
