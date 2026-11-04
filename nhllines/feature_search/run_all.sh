#!/bin/zsh
# Runs every search in order. Usage, from nhllines/feature_search:
#   ./run_all.sh 1            # goalie-free dataset (data/rows_nogoalie.csv)
#   KMAX=4 ./run_all.sh 0     # with goalie features; cap the exhaustive search at 4
cd "${0:A:h}"
PY="${0:A:h}/../.venv/bin/python"
for m in baselines blocks diffblocks forward forward_elo backward floating lasso anneal genetic ctune exhaustive; do
  echo "=== $m ==="
  NO_GOALIE=$1 "$PY" -u search.py $m 2>&1 | grep -v -i "warn" || echo "FAILED $m"
done
echo "ALL DONE"
