"""Train the production model for each crop x checkpoint on the FULL
historical dataset.

Per crop/checkpoint, uses whichever feature approach (see
feature_engineering.best_variant) actually scored better in the CV
comparison: engineered features (county-trend detrending + NDVI/weather
anomalies) proved out for corn/soybean, but hurt wheat -- its much smaller,
NE-concentrated dataset doesn't have enough per-county history to fit a
reliable trend line, so the detrended target ends up noisier, not cleaner.
This is a data-driven choice per crop/checkpoint, not a hardcoded one.

Unlike train_models.py, this isn't a CV evaluation -- it produces the actual
model + auxiliary artifacts predict_live.py needs. For "engineered" crops
that's the per-county trend fits and feature means; for "baseline" crops
there's nothing to persist beyond the variant flag itself, since raw
features need no live transform.
"""
import json
import joblib
from sklearn.ensemble import GradientBoostingRegressor

from config import CROPS, crop_checkpoints
from model_utils import load_checkpoint_table, prep_features, numeric_feature_cols, TARGET
from feature_engineering import fit_county_trends, trend_predict, county_feature_means, \
    add_anomaly_features, STATIC_COLS, best_variant
from build_dataset import NEEDS_STRESS, stress_columns

MODEL_DIR = "models"


def train_and_save(crop: str, checkpoint_name: str):
    raw = load_checkpoint_table(checkpoint_name, crop)
    if (crop, checkpoint_name) not in NEEDS_STRESS:
        # Layer 2 stress columns are merged into every checkpoint table by
        # build_dataset.py, but evaluate_stress_features.py's gate found
        # they only genuinely help these two -- everywhere else, drop them
        # before training so the shipped model matches what was validated.
        raw = raw.drop(columns=stress_columns(raw))
    df, _ = prep_features(raw)  # one-hot encodes state, drops NaN rows
    base_numeric = numeric_feature_cols(raw)
    state_cols = [c for c in df.columns if c.startswith("state_")]

    variant = best_variant(crop, checkpoint_name)

    if variant == "engineered":
        # county-trend detrending: model learns the residual, not raw yield
        dynamic_features = [c for c in base_numeric if c not in STATIC_COLS]
        trends = fit_county_trends(df)
        target = df[TARGET] - trend_predict(df, trends)

        # NDVI/weather anomaly features (skip STATIC_COLS -- see feature_engineering.py)
        county_means = county_feature_means(df, dynamic_features)
        df = add_anomaly_features(df, county_means, dynamic_features)
        df["year_trend"] = df["year"] - df["year"].min()

        features = base_numeric + [f"anom_{c}" for c in dynamic_features] + ["year_trend"] + state_cols
        aux = {
            "variant": "engineered",
            "trends": trends,
            "county_means": county_means,
            "dynamic_features": dynamic_features,
            "min_year": int(df["year"].min()),
        }
    else:
        target = df[TARGET]
        features = base_numeric + state_cols
        aux = {"variant": "baseline"}

    model = GradientBoostingRegressor(n_estimators=300, max_depth=3, random_state=42)
    model.fit(df[features], target)

    joblib.dump(model, f"{MODEL_DIR}/gb_{crop}_{checkpoint_name}.joblib")
    with open(f"{MODEL_DIR}/gb_{crop}_{checkpoint_name}_features.json", "w") as f:
        json.dump(features, f)
    joblib.dump(aux, f"{MODEL_DIR}/gb_{crop}_{checkpoint_name}_aux.joblib")

    print(f"[{crop}/{checkpoint_name}] variant={variant}, trained on {len(df)} rows, "
          f"{len(features)} features -> {MODEL_DIR}/gb_{crop}_{checkpoint_name}.joblib")


if __name__ == "__main__":
    import sys
    crops = sys.argv[1:] or list(CROPS.keys())
    for crop in crops:
        for checkpoint_name in crop_checkpoints(crop):
            train_and_save(crop, checkpoint_name)
