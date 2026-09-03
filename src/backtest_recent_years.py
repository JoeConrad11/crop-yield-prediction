"""Backtest: for 2024 and 2025 (now real, completed seasons with known
actual yield), replay what the early_season and pre_harvest checkpoints
would have predicted if queried at that point in those seasons -- using the
exact same engineered-feature training procedure as train_final_models.py
(county-trend detrending + NDVI/weather anomalies), just held out for
evaluation instead of included in training.

This is the trust check called for in the solidification plan: before this
pipeline's live predictions reach anyone, confirm it would have been
reasonably close on real, recent, already-known seasons.
"""
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score

from config import CHECKPOINTS, CROPS
from model_utils import load_checkpoint_table, prep_features, numeric_feature_cols, TARGET
from feature_engineering import fit_county_trends, trend_predict, county_feature_means, \
    add_anomaly_features, STATIC_COLS

BACKTEST_YEARS = [2024, 2025]


def backtest_one(crop: str, checkpoint_name: str, test_year: int) -> dict:
    raw = load_checkpoint_table(checkpoint_name, crop)
    df, _ = prep_features(raw)
    base_numeric = numeric_feature_cols(raw)
    dynamic_features = [c for c in base_numeric if c not in STATIC_COLS]

    train = df[df["year"] != test_year].copy()
    test = df[df["year"] == test_year].copy()

    trends = fit_county_trends(train)
    train_target = train[TARGET] - trend_predict(train, trends)
    test_trend_pred = trend_predict(test, trends)

    county_means = county_feature_means(train, dynamic_features)
    train = add_anomaly_features(train, county_means, dynamic_features)
    test = add_anomaly_features(test, county_means, dynamic_features)
    train["year_trend"] = train["year"] - train["year"].min()
    test["year_trend"] = test["year"] - train["year"].min()

    state_cols = [c for c in train.columns if c.startswith("state_")]
    features = base_numeric + [f"anom_{c}" for c in dynamic_features] + ["year_trend"] + state_cols

    model = GradientBoostingRegressor(n_estimators=300, max_depth=3, random_state=42)
    model.fit(train[features], train_target)
    preds = model.predict(test[features]) + test_trend_pred

    mae = mean_absolute_error(test[TARGET], preds)
    r2 = r2_score(test[TARGET], preds)
    return {"crop": crop, "checkpoint": checkpoint_name, "test_year": test_year,
            "mae": mae, "r2": r2, "n_counties": len(test)}


if __name__ == "__main__":
    rows = []
    for crop in CROPS:
        for checkpoint_name in CHECKPOINTS:
            for test_year in BACKTEST_YEARS:
                result = backtest_one(crop, checkpoint_name, test_year)
                rows.append(result)
                print(f"[{crop}/{checkpoint_name}/{test_year}] MAE={result['mae']:.2f} "
                      f"R2={result['r2']:.3f} ({result['n_counties']} counties)")

    summary = pd.DataFrame(rows)
    summary.to_csv("data/processed/backtest_2024_2025.csv", index=False)
    print("\nSaved data/processed/backtest_2024_2025.csv")
