"""Backtest: leave-one-year-out held-out predictions for every year in the
training window (config.YEAR_START-YEAR_END), using the exact same
per-crop/checkpoint feature approach (engineered vs. baseline, see
feature_engineering.best_variant) as train_final_models.py -- so this
backtest reflects what's actually shipped to production, not always the
engineered path regardless of whether it helps that crop.

For 2024/2025 specifically this mirrors what the checkpoint would have
predicted if queried live (training on all *other* available years, which
is what production actually does). For earlier years the held-out year is
also excluded from training, but the training set then includes later
years too -- i.e. this is standard leave-one-year-out cross-validation
(same methodology as feature_engineering.py's CV), not a literal replay of
"what was knowable at the time" for anything before 2024. Framed honestly
as "held-out prediction" throughout, not "what we would have said live."

This is the trust check called for in the solidification plan: before this
pipeline's live predictions reach anyone, confirm it would have been
reasonably close on real, known seasons across the whole training window,
not just the two most recent ones.
"""
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score

from config import CHECKPOINTS, CROPS, YEAR_START, YEAR_END
from model_utils import load_checkpoint_table, prep_features, numeric_feature_cols, TARGET
from feature_engineering import fit_county_trends, trend_predict, county_feature_means, \
    add_anomaly_features, STATIC_COLS, best_variant

BACKTEST_YEARS = list(range(YEAR_START, YEAR_END + 1))


def backtest_one(crop: str, checkpoint_name: str, test_year: int) -> tuple:
    """Returns (summary dict, per-county predictions DataFrame) -- the
    per-county numbers are what the frontend's "model accuracy" trend view
    reads (see api/routers/history.py), the summary dict is the aggregate
    trust-check metric this script has always reported.
    """
    raw = load_checkpoint_table(checkpoint_name, crop)
    df, _ = prep_features(raw)
    base_numeric = numeric_feature_cols(raw)

    train = df[df["year"] != test_year].copy()
    test = df[df["year"] == test_year].copy()

    variant = best_variant(crop, checkpoint_name)
    state_cols = [c for c in train.columns if c.startswith("state_")]

    if variant == "engineered":
        dynamic_features = [c for c in base_numeric if c not in STATIC_COLS]
        trends = fit_county_trends(train)
        train_target = train[TARGET] - trend_predict(train, trends)
        test_trend_pred = trend_predict(test, trends)

        county_means = county_feature_means(train, dynamic_features)
        train = add_anomaly_features(train, county_means, dynamic_features)
        test = add_anomaly_features(test, county_means, dynamic_features)
        train["year_trend"] = train["year"] - train["year"].min()
        test["year_trend"] = test["year"] - train["year"].min()

        features = base_numeric + [f"anom_{c}" for c in dynamic_features] + ["year_trend"] + state_cols
    else:
        train_target = train[TARGET]
        test_trend_pred = 0.0
        features = base_numeric + state_cols

    model = GradientBoostingRegressor(n_estimators=300, max_depth=3, random_state=42)
    model.fit(train[features], train_target)
    preds = model.predict(test[features]) + test_trend_pred

    mae = mean_absolute_error(test[TARGET], preds)
    r2 = r2_score(test[TARGET], preds)
    summary = {"crop": crop, "checkpoint": checkpoint_name, "test_year": test_year,
               "mae": mae, "r2": r2, "n_counties": len(test)}

    per_county = pd.DataFrame({
        "crop": crop,
        "checkpoint": checkpoint_name,
        "year": test["year"].values,
        "state_fips": test["state_fips"].astype(str).str.zfill(2).values,
        "county_fips": test["county_fips"].astype(str).str.zfill(3).values,
        "county_name": test["county_name"].values,
        "actual_yield_bu_acre": test[TARGET].values,
        "predicted_yield_bu_acre": preds,
    })
    return summary, per_county


if __name__ == "__main__":
    summary_rows = []
    per_county_frames = []
    for crop in CROPS:
        for checkpoint_name in CHECKPOINTS:
            for test_year in BACKTEST_YEARS:
                result, per_county = backtest_one(crop, checkpoint_name, test_year)
                summary_rows.append(result)
                per_county_frames.append(per_county)
                print(f"[{crop}/{checkpoint_name}/{test_year}] MAE={result['mae']:.2f} "
                      f"R2={result['r2']:.3f} ({result['n_counties']} counties)")

    summary = pd.DataFrame(summary_rows)
    summary.to_csv("data/processed/backtest_summary.csv", index=False)
    print("\nSaved data/processed/backtest_summary.csv")

    per_county_all = pd.concat(per_county_frames, ignore_index=True)
    per_county_all.to_csv("data/processed/backtest_predictions.csv", index=False)
    print(f"Saved {len(per_county_all)} per-county backtest predictions to "
          f"data/processed/backtest_predictions.csv")
