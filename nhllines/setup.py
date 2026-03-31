#!/usr/bin/env python3
"""Quick setup helper - installs dependencies and validates config."""

import subprocess
import sys
import json
from pathlib import Path


def main():
    print("NHL +EV Betting Finder - Setup")
    print("=" * 40)

    # Install requests
    print("\n1. Installing dependencies...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    print("   Done.")

    # Check for API key
    print("\n2. Checking for Odds API key...")
    config_path = Path(__file__).parent / "config.json"

    import os
    if os.environ.get("ODDS_API_KEY"):
        print("   Found ODDS_API_KEY in environment.")
    elif config_path.exists():
        config = json.loads(config_path.read_text())
        if config.get("odds_api_key") and config["odds_api_key"] != "YOUR_API_KEY_HERE":
            print("   Found API key in config.json.")
        else:
            _prompt_key(config_path)
    else:
        _prompt_key(config_path)

    # Quick connectivity test
    print("\n3. Testing NHL API connectivity...")
    try:
        import requests
        resp = requests.get("https://api-web.nhle.com/v1/standings/now", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        n_teams = len(data.get("standings", []))
        print(f"   NHL API working - found {n_teams} teams in standings.")
    except Exception as e:
        print(f"   Warning: NHL API test failed: {e}")
        print("   The tool may not work without internet access to api-web.nhle.com")

    print("\n" + "=" * 40)
    print("Setup complete! Run with:")
    print("  python main.py              # Full analysis (needs API key)")
    print("  python main.py --no-odds    # Model only (no API key needed)")
    print("  python main.py --stake 0.50 # $0.50 bets")


def _prompt_key(config_path):
    print("   No API key found.")
    print("   Sign up free at: https://the-odds-api.com")
    print("   Then either:")
    print("     a) Set env var: export ODDS_API_KEY=your_key")
    print(f"    b) Copy config.json.example to config.json and add your key")
    key = input("\n   Enter your API key now (or press Enter to skip): ").strip()
    if key:
        config_path.write_text(json.dumps({"odds_api_key": key}, indent=2))
        print(f"   Saved to {config_path}")
    else:
        print("   Skipped. You can run with --no-odds flag for now.")


if __name__ == "__main__":
    main()
