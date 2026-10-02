"""
Live performance record: logged predictions scored against final scores.
=========================================================================
Each main.py run calls update_performance() with the completed games it
already fetched. Every prediction in data/predictions_log.jsonl whose game
has a final score becomes one scored result in data/performance.json, which
the site's Performance History tab reads.

Results accumulate: once a game is scored it stays in performance.json even
after it ages out of the run's recent-games window, so the file is the
season's full record. Where a game was logged more than once (one row per
slate per game), the latest pre-game row is the one scored.

The old retrospective backtest (data/backtest_results.json, the similarity
model replayed over Mar-Jun 2026) is carried in as its own season, labelled
as a backtest, so it stays viewable without being mixed into live results.
"""

import json
from datetime import datetime
from pathlib import Path

from src.data.nhl_data import ET

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LOG_PATH = DATA_DIR / "predictions_log.jsonl"
OUT_PATH = DATA_DIR / "performance.json"
BACKTEST_PATH = DATA_DIR / "backtest_results.json"


def season_of(date: str) -> str:
    """'2026-10-01' -> '2026-27' (seasons start in July for this purpose)."""
    y, m = int(date[:4]), int(date[5:7])
    start = y if m >= 7 else y - 1
    return f"{start}-{str(start + 1)[2:]}"


def _key(date, home, away) -> str:
    return f"{date}|{away}@{home}"


def _latest_predictions(log_path: Path) -> dict:
    latest = {}
    if not log_path.exists():
        return latest
    for line in log_path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        k = _key(r.get("date"), r.get("home_team"), r.get("away_team"))
        if k not in latest or r.get("timestamp_utc", "") > latest[k].get("timestamp_utc", ""):
            latest[k] = r
    return latest


def _score(pred: dict, game: dict) -> dict:
    home, away = pred["home_team"], pred["away_team"]
    hs, as_ = game["home_score"], game["away_score"]
    p_home = float(pred["home_win_prob"])
    predicted_winner = home if p_home > 0.5 else away
    actual_winner = home if hs > as_ else away
    exp_total = pred.get("expected_total")
    actual_total = hs + as_
    return {
        "date": pred["date"],
        "season": season_of(pred["date"]),
        "source": "live",
        "game": f"{away} @ {home}",
        "home": home,
        "away": away,
        "predicted_home_win_prob": round(p_home, 3),
        "predicted_winner": predicted_winner,
        "actual_winner": actual_winner,
        "winner_correct": predicted_winner == actual_winner,
        "predicted_total": round(float(exp_total), 2) if exp_total is not None else None,
        "actual_total": actual_total,
        "total_error": round(abs(float(exp_total) - actual_total), 2) if exp_total is not None else None,
        "actual_score": f"{as_}-{hs}",
        "model_version": pred.get("model_version", ""),
    }


def _legacy_backtest(path: Path) -> list:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    out = []
    for r in data.get("results", []):
        out.append(dict(r, season=season_of(r["date"]), source="backtest"))
    return out


def update_performance(completed_games: list, log_path: Path = LOG_PATH,
                       out_path: Path = OUT_PATH,
                       backtest_path: Path = BACKTEST_PATH) -> dict:
    """Score newly completed logged predictions and rewrite performance.json.
    `completed_games` are nhl_data.fetch_season_games() rows (date,
    home_team, away_team, home_score, away_score). Returns the written dict."""
    try:
        existing = json.loads(out_path.read_text())
    except (OSError, ValueError):
        existing = {}
    live = {_key(r["date"], r["home"], r["away"]): r
            for r in existing.get("results", []) if r.get("source") == "live"}

    finals = {}
    for g in completed_games:
        if g.get("home_score") is None or g.get("away_score") is None:
            continue
        finals[_key(g.get("date", "")[:10], g.get("home_team"), g.get("away_team"))] = g

    new = 0
    for k, pred in _latest_predictions(log_path).items():
        if k in finals and k not in live:
            live[k] = _score(pred, finals[k])
            new += 1

    results = sorted(list(live.values()) + _legacy_backtest(backtest_path),
                     key=lambda r: (r["date"], r["game"]), reverse=True)
    seasons = []
    for s in sorted({r["season"] for r in results}, reverse=True):
        sources = {r["source"] for r in results if r["season"] == s}
        label = s if "live" in sources else f"{s} (backtest)"
        seasons.append({"key": s, "label": label})

    out = {
        "generated_at": datetime.now(ET).isoformat(),
        "seasons": seasons,
        "results": results,
    }
    out_path.write_text(json.dumps(out, indent=2))
    n_live = sum(1 for r in results if r["source"] == "live")
    print(f"Performance: scored {new} new game(s); {n_live} live result(s) "
          f"in {out_path.name}")
    return out
