import json
import os
from datetime import datetime

FEEDBACK_PATH = os.path.join(os.path.dirname(__file__), "../../mlbdata/model_feedback.json")

DEFAULT_FEEDBACK = {
    "bet_type_accuracy": {
        "Moneyline": {"correct": 15, "total": 45},
        "Total": {"correct": 42, "total": 77},
    },
    "optimal_weights": {
        "confidence_scaling": 1.0,
        "model_weight": 0.45,
    },
    "last_updated": None,
}

# Edge required given a bet type's historical win rate
def _required_edge(win_rate: float, bet_type: str) -> float:
    if bet_type == "Moneyline":
        if win_rate < 0.40:
            return 0.08
        elif win_rate < 0.48:
            return 0.06
        else:
            return 0.04
    else:  # Total / Run Line
        if win_rate > 0.52:
            return 0.025
        elif win_rate >= 0.48:
            return 0.03
        else:
            return 0.04


class MLBModelFeedback:
    def __init__(self):
        self.data = self._load()

    def _load(self) -> dict:
        path = os.path.abspath(FEEDBACK_PATH)
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
        return dict(DEFAULT_FEEDBACK)

    def save(self):
        path = os.path.abspath(FEEDBACK_PATH)
        self.data["last_updated"] = datetime.now().isoformat()
        with open(path, "w") as f:
            json.dump(self.data, f, indent=2)

    def record_result(self, bet_type: str, won: bool):
        acc = self.data["bet_type_accuracy"]
        if bet_type not in acc:
            acc[bet_type] = {"correct": 0, "total": 0}
        acc[bet_type]["total"] += 1
        if won:
            acc[bet_type]["correct"] += 1
        self.save()

    def should_take_bet(self, edge: float, confidence: float, bet_type: str) -> bool:
        if confidence < 0.40:
            return False

        acc = self.data["bet_type_accuracy"].get(bet_type, {})
        total = acc.get("total", 0)
        if total >= 10:
            win_rate = acc["correct"] / total
            req = _required_edge(win_rate, bet_type)
            if edge < req:
                return False

        return True

    def get_stats(self) -> dict:
        out = {}
        for bt, rec in self.data["bet_type_accuracy"].items():
            t = rec.get("total", 0)
            c = rec.get("correct", 0)
            out[bt] = {"win_rate": c / t if t else None, "total": t}
        return out

    def print_summary(self):
        print("\n  [MLB Feedback System]")
        for bt, s in self.get_stats().items():
            wr = f"{s['win_rate']:.1%}" if s["win_rate"] is not None else "N/A"
            print(f"    {bt}: {wr} WR ({s['total']} bets)")
