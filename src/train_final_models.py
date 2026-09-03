"""Train the production model for each crop x checkpoint on the FULL
historical dataset, using the validated engineered features (county-trend
detrending + NDVI/weather anomalies from feature_engineering.py) instead of
raw features -- these were proven in feature_engineering.py's CV comparison
to help RF/MLP meaningfully, but were never shipped to production until now.

Unlike train_models.py, this isn't a CV evaluation -- it produces the actual
model + auxiliary artifacts (per-county trend fits, per-county feature means)
that predict_live.py needs to apply the identical transforms to a live,
current-season county.
"""
import json
import joblib
from sklearn.ensemble import GradientBoostingRegressor

from config import CHECKPOINTS, CROPS
from model_utils import load_checkpoint_table, prep_features, numeric_feature_cols, TARGET
from feature_engineering import fit_county_trends, trend_predict, county_feature_means, \
    add_anomaly_features, STATIC_COLS

MODEL_DIR = "models"


def train_and_save(crop: str, checkpoint_name: str):
    raw = load_checkpoint_table(checkpoint_name, crop)
    df, _ = prep_features(raw)  # one-hot encodes state, drops NaN rows
    base_numeric = numeric_feature_cols(raw)
    dynamic_features = [c for c in base_numeric if c not in STATIC_COLS]

    # county-trend detrending: model learns the residual, not raw yield
    trends = fit_county_trends(df)
    target_resid = df[TARGET] - trend_predict(df, trends)

    # NDVI/weather anomaly features (skip STATIC_COLS -- see feature_engineering.py)
    county_means = county_feature_means(df, dynamic_features)
    df = add_anomaly_features(df, county_means, dynamic_features)
    df["year_trend"] = df["year"] - df["year"].min()

    state_cols = [c for c in df.columns if c.startswith("state_")]
    features = base_numeric + [f"anom_{c}" for c in dynamic_features] + ["year_trend"] + state_cols

    model = GradientBoostingRegressor(n_estimators=300, max_depth=3, random_state=42)
    model.fit(df[features], target_resid)

    joblib.dump(model, f"{MODEL_DIR}/gb_{crop}_{checkpoint_name}.joblib")
    with open(f"{MODEL_DIR}/gb_{crop}_{checkpoint_name}_features.json", "w") as f:
        json.dump(features, f)
    joblib.dump({
        "trends": trends,
        "county_means": county_means,
        "dynamic_features": dynamic_features,
        "min_year": int(df["year"].min()),
    }, f"{MODEL_DIR}/gb_{crop}_{checkpoint_name}_aux.joblib")

    print(f"[{crop}/{checkpoint_name}] trained on {len(df)} rows, {len(features)} engineered features -> "
          f"{MODEL_DIR}/gb_{crop}_{checkpoint_name}.joblib")


if __name__ == "__main__":
    import sys
    crops = sys.argv[1:] or list(CROPS.keys())
    for crop in crops:
        for checkpoint_name in CHECKPOINTS:
            train_and_save(crop, checkpoint_name)
