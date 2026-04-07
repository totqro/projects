"""
Model Feedback System
=====================
Tracks model prediction accuracy and uses results to improve future predictions.

Features:
- Calibration tracking: Are 60% predictions actually winning 60% of the time?
- Context-specific accuracy: Which factors (injuries, B2B, goalies) are most predictive?
- Dynamic weight adjustment: Adjust model/market blend based on recent performance
- Confidence recalibration: Learn when the model is over/underconfident
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict
import math


FEEDBACK_PATH = Path(__file__).parent.parent.parent / "data" / "model_feedback.json"


class ModelFeedback:
    """Tracks and learns from model prediction accuracy."""
    
    def __init__(self):
        self.feedback_data = self._load_feedback()
    
    def _load_feedback(self) -> dict:
        """Load existing feedback data or create new structure."""
        if FEEDBACK_PATH.exists():
            return json.loads(FEEDBACK_PATH.read_text())
        
        return {
            "calibration_bins": {},  # prob_bin -> {correct, total}
            "context_accuracy": {},  # context_type -> {correct, total}
            "model_vs_market": {     # Track when model beats market
                "model_better": 0,
                "market_better": 0,
                "tie": 0
            },
            "confidence_accuracy": {},  # confidence_bin -> {correct, total}
            "bet_type_accuracy": {},    # bet_type -> {correct, total}
            "recent_performance": [],   # Last 100 predictions
            "processed_bets": [],       # IDs of already-processed bets
            "optimal_weights": {
                "model_weight": 0.65,
                "confidence_scaling": 1.0,
                "context_adjustments": {}
            },
            "last_updated": None
        }
    
    def _save_feedback(self):
        """Save feedback data to disk."""
        FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.feedback_data["last_updated"] = datetime.now().isoformat()
        FEEDBACK_PATH.write_text(json.dumps(self.feedback_data, indent=2))
    
    def update_from_results(self, bet_results: dict):
        """
        Update feedback system with actual bet results.
        
        Args:
            bet_results: Dict from bet_results.json with resolved bets
        """
        print("\n[Feedback] Updating model with bet results...")

        # Ensure processed_bets list exists (for data files created before this field)
        if "processed_bets" not in self.feedback_data:
            self.feedback_data["processed_bets"] = []
        processed = set(self.feedback_data["processed_bets"])

        updated_count = 0
        for bet_id, result in bet_results.items():
            if bet_id in processed:
                continue  # Already processed this bet

            bet = result["bet"]
            outcome = result["result"]

            if outcome == "push":
                processed.add(bet_id)
                continue  # Skip pushes
            
            won = (outcome == "won")
            
            # Extract prediction details
            true_prob = bet.get("true_prob", 0.5)
            confidence = bet.get("confidence", 0.5)
            bet_type = bet.get("bet_type", "Unknown")
            edge = bet.get("edge", 0)
            
            # Update calibration bins (group by 5% buckets)
            # Use string keys for JSON compatibility
            prob_bin = str(int(true_prob * 20) * 5)  # "0", "5", ..., "95", "100"
            if prob_bin not in self.feedback_data["calibration_bins"]:
                self.feedback_data["calibration_bins"][prob_bin] = {"correct": 0, "total": 0}

            self.feedback_data["calibration_bins"][prob_bin]["total"] += 1
            if won:
                self.feedback_data["calibration_bins"][prob_bin]["correct"] += 1

            # Update confidence bins
            conf_bin = str(int(confidence * 10) * 10)  # "0", "10", ..., "90", "100"
            if conf_bin not in self.feedback_data["confidence_accuracy"]:
                self.feedback_data["confidence_accuracy"][conf_bin] = {"correct": 0, "total": 0}

            self.feedback_data["confidence_accuracy"][conf_bin]["total"] += 1
            if won:
                self.feedback_data["confidence_accuracy"][conf_bin]["correct"] += 1
            
            # Update bet type accuracy
            if bet_type not in self.feedback_data["bet_type_accuracy"]:
                self.feedback_data["bet_type_accuracy"][bet_type] = {"correct": 0, "total": 0}
            
            self.feedback_data["bet_type_accuracy"][bet_type]["total"] += 1
            if won:
                self.feedback_data["bet_type_accuracy"][bet_type]["correct"] += 1
            
            # Track recent performance (rolling window)
            self.feedback_data["recent_performance"].append({
                "bet_id": bet_id,
                "won": won,
                "true_prob": true_prob,
                "confidence": confidence,
                "edge": edge,
                "bet_type": bet_type,
                "timestamp": result.get("checked_at")
            })
            
            # Keep only last 100
            if len(self.feedback_data["recent_performance"]) > 100:
                self.feedback_data["recent_performance"] = \
                    self.feedback_data["recent_performance"][-100:]

            processed.add(bet_id)
            updated_count += 1

        self.feedback_data["processed_bets"] = list(processed)
        
        if updated_count > 0:
            self._recalculate_optimal_weights()
            self._save_feedback()
            print(f"[Feedback] Updated with {updated_count} results")
            self._print_calibration_report()
        else:
            print("[Feedback] No new results to process")
    
    def _recalculate_optimal_weights(self):
        """Recalculate optimal model/market blend based on performance."""
        recent = self.feedback_data["recent_performance"]
        
        if len(recent) < 20:
            return  # Need more data
        
        # Calculate Brier score (lower is better)
        # Brier = avg((predicted_prob - actual_outcome)^2)
        brier_scores = []
        for pred in recent:
            predicted = pred["true_prob"]
            actual = 1.0 if pred["won"] else 0.0
            brier_scores.append((predicted - actual) ** 2)
        
        avg_brier = sum(brier_scores) / len(brier_scores)
        
        # If Brier score is good (< 0.20), trust model more
        # If Brier score is poor (> 0.25), trust market more
        if avg_brier < 0.20:
            # Model is well-calibrated, increase weight
            current_weight = self.feedback_data["optimal_weights"]["model_weight"]
            new_weight = min(0.75, current_weight + 0.02)
            self.feedback_data["optimal_weights"]["model_weight"] = new_weight
        elif avg_brier > 0.25:
            # Model is poorly calibrated, decrease weight
            current_weight = self.feedback_data["optimal_weights"]["model_weight"]
            new_weight = max(0.50, current_weight - 0.02)
            self.feedback_data["optimal_weights"]["model_weight"] = new_weight
        
        # Adjust confidence scaling based on calibration
        # If model is overconfident, scale down confidence
        # If model is underconfident, scale up confidence
        calibration_error = self._calculate_calibration_error()
        if calibration_error > 0.05:  # Overconfident
            self.feedback_data["optimal_weights"]["confidence_scaling"] = \
                max(0.7, self.feedback_data["optimal_weights"]["confidence_scaling"] - 0.05)
        elif calibration_error < -0.05:  # Underconfident
            self.feedback_data["optimal_weights"]["confidence_scaling"] = \
                min(1.3, self.feedback_data["optimal_weights"]["confidence_scaling"] + 0.05)
    
    def _calculate_calibration_error(self) -> float:
        """
        Calculate calibration error: difference between predicted and actual win rates.
        Positive = overconfident, Negative = underconfident
        """
        bins = self.feedback_data["calibration_bins"]
        
        if not bins:
            return 0.0
        
        total_error = 0
        total_weight = 0
        
        for prob_bin, data in bins.items():
            if data["total"] < 5:
                continue  # Skip bins with too few samples

            predicted_prob = int(prob_bin) / 100.0
            actual_prob = data["correct"] / data["total"]
            error = predicted_prob - actual_prob
            
            # Weight by sample size
            weight = data["total"]
            total_error += error * weight
            total_weight += weight
        
        return total_error / total_weight if total_weight > 0 else 0.0
    
    def get_adjusted_confidence(self, raw_confidence: float) -> float:
        """
        Adjust confidence based on historical calibration.
        
        Args:
            raw_confidence: Model's raw confidence score
            
        Returns:
            Calibrated confidence score
        """
        scaling = self.feedback_data["optimal_weights"]["confidence_scaling"]
        
        # Apply scaling but keep in valid range
        adjusted = raw_confidence * scaling
        
        # Ensure stays in [0.3, 0.95] range
        return max(0.3, min(0.95, adjusted))
    
    def get_optimal_model_weight(self) -> float:
        """Get the current optimal model/market blend weight."""
        return self.feedback_data["optimal_weights"]["model_weight"]
    
    def _print_calibration_report(self):
        """Print calibration statistics."""
        print("\n" + "=" * 60)
        print("  MODEL CALIBRATION REPORT")
        print("=" * 60)
        
        # Overall accuracy
        recent = self.feedback_data["recent_performance"]
        if recent:
            wins = sum(1 for p in recent if p["won"])
            total = len(recent)
            win_rate = wins / total
            print(f"\n  Recent Performance (last {total} bets):")
            print(f"    Win Rate: {win_rate:.1%} ({wins}W-{total-wins}L)")
            
            # Calculate expected win rate from probabilities
            expected_wins = sum(p["true_prob"] for p in recent)
            expected_rate = expected_wins / total
            print(f"    Expected: {expected_rate:.1%}")
            print(f"    Difference: {(win_rate - expected_rate):+.1%}")
        
        # Calibration by probability bin
        print("\n  Calibration by Predicted Probability:")
        print("  " + "-" * 56)
        bins = self.feedback_data["calibration_bins"]
        for prob_bin in sorted(bins.keys(), key=int):
            data = bins[prob_bin]
            if data["total"] < 3:
                continue

            predicted = int(prob_bin) / 100.0
            actual = data["correct"] / data["total"]
            diff = actual - predicted
            
            print(f"    {int(prob_bin):3d}%: {actual:.1%} actual "
                  f"({data['correct']}/{data['total']}) "
                  f"[{diff:+.1%}]")
        
        # Bet type performance
        print("\n  Performance by Bet Type:")
        print("  " + "-" * 56)
        bet_types = self.feedback_data["bet_type_accuracy"]
        for bet_type, data in sorted(bet_types.items()):
            if data["total"] < 3:
                continue
            
            win_rate = data["correct"] / data["total"]
            print(f"    {bet_type:12s}: {win_rate:.1%} "
                  f"({data['correct']}/{data['total']})")
        
        # Current optimal weights
        print("\n  Optimal Weights:")
        print("  " + "-" * 56)
        weights = self.feedback_data["optimal_weights"]
        print(f"    Model Weight: {weights['model_weight']:.2f}")
        print(f"    Confidence Scaling: {weights['confidence_scaling']:.2f}")
        
        calibration_error = self._calculate_calibration_error()
        if calibration_error > 0.05:
            print(f"    ⚠️  Model is OVERCONFIDENT by {calibration_error:.1%}")
        elif calibration_error < -0.05:
            print(f"    ⚠️  Model is UNDERCONFIDENT by {abs(calibration_error):.1%}")
        else:
            print(f"    ✅ Model is well-calibrated ({calibration_error:+.1%})")
        
        print("=" * 60 + "\n")
    
    def should_take_bet(self, edge: float, confidence: float, bet_type: str) -> bool:
        """
        Use historical performance to decide if a bet is worth taking.
        
        Args:
            edge: Predicted edge
            confidence: Model confidence
            bet_type: Type of bet (Moneyline, Total, Spread)
            
        Returns:
            True if bet meets learned criteria
        """
        # Check bet type historical performance
        type_data = self.feedback_data["bet_type_accuracy"].get(bet_type, {})
        if type_data.get("total", 0) >= 10:
            type_win_rate = type_data["correct"] / type_data["total"]
            
            # If this bet type historically underperforms, require higher edge
            # Optimized: Totals at 42.9% WR need 6%+ edge, ML at 52.3% WR is fine at 4%
            if type_win_rate < 0.50:
                edge_threshold = 0.06  # Require 6%+ edge for underperforming bet types
            else:
                edge_threshold = 0.04  # Standard 4%+ edge
            
            if edge < edge_threshold:
                return False
        
        # Check confidence level performance
        conf_bin = str(int(confidence * 10) * 10)
        conf_data = self.feedback_data["confidence_accuracy"].get(conf_bin, {})
        if conf_data.get("total", 0) >= 10:
            conf_win_rate = conf_data["correct"] / conf_data["total"]
            
            # If low confidence bets historically lose, skip them
            if confidence < 0.60 and conf_win_rate < 0.45:
                return False
        
        return True


# Global instance
_feedback_instance = None


def get_feedback_system() -> ModelFeedback:
    """Get or create the global feedback system instance."""
    global _feedback_instance
    if _feedback_instance is None:
        _feedback_instance = ModelFeedback()
    return _feedback_instance


def update_model_from_results():
    """Update model feedback from bet_results.json."""
    from src.analysis.bet_tracker import BET_LOG_PATH
    
    if not BET_LOG_PATH.exists():
        print("[Feedback] No bet results found")
        return
    
    results_log = json.loads(BET_LOG_PATH.read_text())
    results = results_log.get("results", {})
    
    if not results:
        print("[Feedback] No resolved bets to learn from")
        return
    
    feedback = get_feedback_system()
    feedback.update_from_results(results)


if __name__ == "__main__":
    # Run feedback update
    update_model_from_results()
