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
    result = pd.concat(frames, ignore_index=True)

    # Merge with existing rows for crops not in this run -- a partial run
    # (e.g. `train_models.py wheat`) shouldn't silently drop other crops'
    # rows from the saved comparison.
    out_path = "data/processed/model_comparison_summary.csv"
    try:
        existing = pd.read_csv(out_path)
        existing = existing[~existing["crop"].isin(crops)]
        result = pd.concat([existing, result], ignore_index=True)
    except FileNotFoundError:
        pass

    result.to_csv(out_path, index=False)
    print(f"\nSaved {out_path} ({sorted(result['crop'].unique())})")
