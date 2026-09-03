"""Compare models (linear, random forest, gradient boosting, small MLP) on
each season checkpoint, using leave-one-year-out CV. See model_utils.py for
the shared model/eval logic (also used by the exploration notebook)."""
import sys
import pandas as pd

from config import CROPS
from model_utils import run_all_checkpoints

if __name__ == "__main__":
    crops = sys.argv[1:] or list(CROPS.keys())
    frames = []
    for crop in crops:
        summary = run_all_checkpoints(crop)
        print(f"\n=== {crop} ===")
        print(summary.to_string(index=False))
        frames.append(summary)
    pd.concat(frames, ignore_index=True).to_csv("data/processed/model_comparison_summary.csv", index=False)
