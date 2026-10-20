#!/usr/bin/env bash
# Copy the published game sheets (the orphan branch xg-sheets-data, rebuilt
# after every game by .github/workflows/xg-game-sheets.yml) into data/, where
# the build reads them. Run from anywhere inside the repo.
set -euo pipefail
cd "$(dirname "$0")/.."
git fetch -q --depth 1 origin xg-sheets-data
rm -rf data && mkdir -p data
git archive FETCH_HEAD | tar -x -C data
echo "data/: seasons $(cat data/seasons.json)"
