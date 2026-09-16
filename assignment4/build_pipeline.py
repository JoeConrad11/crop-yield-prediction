"""Fits the county-yield-anomaly Pipeline and dumps it as a bundle artifact
(Assignment 4).

Trains on the same corn/early_season checkpoint table the production
crop-yield-prediction app uses (real NASS yields, real NDVI/weather/stress
features, ~4,700 county-years) -- this is a genuinely fitted model, not a
toy. Only reads from data/processed/, writes nothing back to the main
project.

Run: python assignment4/build_pipeline.py
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd
import sklearn
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.pipeline import Pipeline

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_def import CountyAnomalyTransformer

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_TABLE = REPO_ROOT / "data/processed/model_table_corn_early_season.csv"

GROUP_COLS = ["state_fips", "county_fips"]
VALUE_COLS = [
    "ndvi_jun", "ndvi_jul",
    "precip_sum_jun", "precip_sum_jul",
    "tmean_jun", "tmean_jul",
    "edd_29c_jul", "dry_days_jul",
]
STATIC_COLS = ["soil_organic_carbon", "soil_ph", "elevation_m", "slope_deg"]
TARGET = "yield_bu_acre"


def build() -> dict:
    df = pd.read_csv(SOURCE_TABLE)
    needed = GROUP_COLS + ["year"] + VALUE_COLS + STATIC_COLS + [TARGET]
    df = df.dropna(subset=needed)

    X = df[GROUP_COLS + ["year"] + VALUE_COLS + STATIC_COLS]
    y = df[TARGET]

    pipeline = Pipeline([
        ("anomaly", CountyAnomalyTransformer(
            group_cols=GROUP_COLS, value_cols=VALUE_COLS, passthrough_cols=STATIC_COLS,
        )),
        ("model", GradientBoostingRegressor(n_estimators=200, max_depth=3, random_state=42)),
    ])
    pipeline.fit(X, y)

    bundle = {
        "pipeline": pipeline,
        "group_cols": GROUP_COLS,
        "value_cols": VALUE_COLS,
        "static_cols": STATIC_COLS,
        "target": TARGET,
        "metadata": {
            "steps": [name for name, _ in pipeline.steps],
            "built_at": datetime.now(timezone.utc).isoformat(),
            "sklearn_version": sklearn.__version__,
            "n_train_rows": int(len(X)),
            "n_counties": int(df.groupby(GROUP_COLS).ngroups),
            "source": "crop-yield-prediction: corn/early_season checkpoint (real NASS yields)",
        },
    }
    return bundle


if __name__ == "__main__":
    bundle = build()
    out_path = Path(__file__).resolve().parent / "pipeline.joblib"
    joblib.dump(bundle, out_path)
    print(f"Saved {out_path}")
    print(f"  rows={bundle['metadata']['n_train_rows']} counties={bundle['metadata']['n_counties']} "
          f"sklearn={bundle['metadata']['sklearn_version']}")
