"""Agronomy Layer 2 evaluation: do the threshold stress metrics actually
improve accuracy, or just add columns?

Same discipline as Phase 4a's yield gate (validate_sentinel2_ndvi.py) --
domain plausibility is not evidence. Extreme degree days are extremely
well supported in the literature (Schlenker & Roberts 2009), and the raw
signal here is dramatic (Iowa July 2012: EDD 132, 24 days above 30C; 2014:
EDD 8.5, 3 days). None of that establishes that THIS model, which already
has tmax/tmean per period plus soil moisture, gains anything from them.
It may already be capturing the same variance by other means.

Method: identical leave-one-year-out CV to the production evaluation, run
on the same table with and without the stress columns, per crop and
checkpoint. Compares the shipped GradientBoosting configuration only.
"""
import sys

import pandas as pd

from build_dataset import stress_columns
from config import CROPS, crop_checkpoints
from model_utils import load_checkpoint_table, prep_features, leave_one_year_out_eval, MODELS
from feature_engineering import (
    leave_one_year_out_eval_engineered, numeric_feature_cols, STATIC_COLS,
)


def compare(crop: str, checkpoint_name: str) -> dict:
    df = load_checkpoint_table(checkpoint_name, crop)
    stress = stress_columns(df)
    if not stress:
        return {"crop": crop, "checkpoint": checkpoint_name, "error": "no stress columns in table"}

    factory = MODELS["GradientBoosting"]
    without = df.drop(columns=stress)

    rows = {"crop": crop, "checkpoint": checkpoint_name, "n_stress_features": len(stress)}

    # baseline variant (raw levels, no anomaly/detrend transform)
    for label, table in (("without", without), ("with", df)):
        prepped, features = prep_features(table)
        result = leave_one_year_out_eval(prepped, features, factory)
        rows[f"baseline_mae_{label}"] = result["mae"].mean()
        rows[f"baseline_r2_{label}"] = result["r2"].median()

    # engineered variant (county anomalies + detrending) -- the one actually
    # shipped for corn/soybeans, so this is the number that matters most
    for label, table in (("without", without), ("with", df)):
        prepped, _ = prep_features(table)
        result = leave_one_year_out_eval_engineered(
            prepped, numeric_feature_cols(table), factory, static_features=STATIC_COLS
        )
        rows[f"engineered_mae_{label}"] = result["mae"].mean()
        rows[f"engineered_r2_{label}"] = result["r2"].median()

    for variant in ("baseline", "engineered"):
        rows[f"{variant}_mae_delta"] = rows[f"{variant}_mae_with"] - rows[f"{variant}_mae_without"]
    return rows


if __name__ == "__main__":
    crops = sys.argv[1:] or list(CROPS.keys())
    all_rows = []
    for crop in crops:
        for checkpoint_name in crop_checkpoints(crop):
            print(f"=== {crop} / {checkpoint_name} ===", flush=True)
            row = compare(crop, checkpoint_name)
            all_rows.append(row)
            if "error" in row:
                print(f"  {row['error']}", flush=True)
                continue
            for variant in ("baseline", "engineered"):
                delta = row[f"{variant}_mae_delta"]
                verdict = "BETTER" if delta < 0 else "worse"
                print(f"  {variant:11} MAE {row[f'{variant}_mae_without']:.3f} -> "
                       f"{row[f'{variant}_mae_with']:.3f}  ({delta:+.3f}, {verdict})   "
                       f"R2 {row[f'{variant}_r2_without']:.3f} -> {row[f'{variant}_r2_with']:.3f}",
                       flush=True)

    out = pd.DataFrame(all_rows)
    out_path = "data/processed/stress_feature_comparison.csv"
    out.to_csv(out_path, index=False)
    print(f"\nSaved {out_path}")
