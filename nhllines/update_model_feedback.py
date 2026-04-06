#!/usr/bin/env python3
"""
Update Model Feedback
=====================
Manually update the model's learning system with bet results.

This script:
1. Reads bet_results.json
2. Calculates calibration metrics
3. Adjusts model/market blend weights
4. Recalibrates confidence scores
5. Identifies which bet types/contexts perform best

Usage:
    python update_model_feedback.py
"""

from src.analysis.model_feedback import update_model_from_results

if __name__ == "__main__":
    print("=" * 60)
    print("  Model Feedback Update")
    print("=" * 60)
    print()
    
    update_model_from_results()
    
    print("\n✅ Model feedback updated successfully")
    print("\nThe model will now use learned weights in future analyses.")
