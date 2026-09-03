"""Baseline model: predict county corn yield from NDVI + weather features.

Uses leave-one-year-out CV so the model is never trained and tested on
the same growing season (avoids leaking year-level yield trends).
"""
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score

DATA_PATH = "data/processed/model_table_ia_corn_2010_2023.csv"
FEATURES = ["ndvi_corn_mean", "precip_sum_mm", "tmean_c", "tmax_c", "tmin_c"]
TARGET = "yield_bu_acre"


def leave_one_year_out_eval(df: pd.DataFrame, model_factory) -> pd.DataFrame:
    results = []
    for test_year in sorted(df["year"].unique()):
        train = df[df["year"] != test_year]
        test = df[df["year"] == test_year]
        model = model_factory()
        model.fit(train[FEATURES], train[TARGET])
        preds = model.predict(test[FEATURES])
        mae = mean_absolute_error(test[TARGET], preds)
        r2 = r2_score(test[TARGET], preds)
        results.append({"held_out_year": test_year, "mae": mae, "r2": r2, "n_test": len(test)})
    return pd.DataFrame(results)


if __name__ == "__main__":
    df = pd.read_csv(DATA_PATH).dropna(subset=FEATURES + [TARGET])

    print("=== Linear Regression (leave-one-year-out) ===")
    lr_results = leave_one_year_out_eval(df, lambda: LinearRegression())
    print(lr_results)
    print(f"Mean MAE: {lr_results['mae'].mean():.2f} bu/acre, Mean R2: {lr_results['r2'].mean():.3f}\n")

    print("=== Random Forest (leave-one-year-out) ===")
    rf_results = leave_one_year_out_eval(df, lambda: RandomForestRegressor(n_estimators=300, random_state=42))
    print(rf_results)
    print(f"Mean MAE: {rf_results['mae'].mean():.2f} bu/acre, Mean R2: {rf_results['r2'].mean():.3f}\n")

    # feature importance from a model trained on everything, just for signal
    rf_full = RandomForestRegressor(n_estimators=300, random_state=42)
    rf_full.fit(df[FEATURES], df[TARGET])
    importances = pd.Series(rf_full.feature_importances_, index=FEATURES).sort_values(ascending=False)
    print("=== Feature importances (RF, full fit) ===")
    print(importances)
