"""Engineered features to address the two biggest known gaps in the baseline:

1. No time trend -- corn yields have a slow multi-decade upward trend from
   genetics/practices improvements that has nothing to do with a given year's
   weather. The baseline model never sees `year` as a feature at all.
2. Raw (not anomaly) NDVI/weather -- two counties with identical NDVI can have
   very different yield potential (soil, management), so the model has to
   waste capacity learning per-county baselines instead of just the
   year-to-year weather signal.

Both the per-county yield trend and the per-county feature means are fit on
the TRAINING fold only inside each CV split, so nothing about the held-out
year leaks into how the trend/anomaly is computed for it.
"""
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, r2_score

from model_utils import ID_COLS, TARGET, numeric_feature_cols, MODELS
from build_dataset import SOIL_COLS, TERRAIN_COLS, NEEDS_STRESS, stress_columns

STATIC_COLS = SOIL_COLS + TERRAIN_COLS

MIN_TREND_POINTS = 4  # need at least this many training years for a county to fit its own trend


def fit_county_trends(train_df: pd.DataFrame) -> dict:
    """Per-(state,county) OLS yield ~ year. Falls back to the global trend if
    a county has too few training years."""
    global_slope, global_intercept = np.polyfit(train_df["year"], train_df[TARGET], 1)
    trends = {}
    for key, group in train_df.groupby(["state_fips", "county_fips"]):
        if len(group) >= MIN_TREND_POINTS:
            slope, intercept = np.polyfit(group["year"], group[TARGET], 1)
        else:
            slope, intercept = global_slope, global_intercept
        trends[key] = (slope, intercept)
    trends["__global__"] = (global_slope, global_intercept)
    return trends


def trend_predict(df: pd.DataFrame, trends: dict) -> np.ndarray:
    preds = np.empty(len(df))
    for i, row in enumerate(df.itertuples()):
        key = (row.state_fips, row.county_fips)
        slope, intercept = trends.get(key, trends["__global__"])
        preds[i] = slope * row.year + intercept
    return preds


def county_feature_means(train_df: pd.DataFrame, feature_cols: list) -> pd.DataFrame:
    return train_df.groupby(["state_fips", "county_fips"])[feature_cols].mean()


def add_anomaly_features(df: pd.DataFrame, county_means: pd.DataFrame, feature_cols: list) -> pd.DataFrame:
    df = df.copy()
    means = df.set_index(["state_fips", "county_fips"]).index.map(
        lambda k: county_means.loc[k] if k in county_means.index else county_means.mean()
    )
    means_df = pd.DataFrame(list(means), columns=feature_cols, index=df.index)
    for col in feature_cols:
        df[f"anom_{col}"] = df[col] - means_df[col]
    return df


def leave_one_year_out_eval_engineered(df: pd.DataFrame, base_features: list, model_factory,
                                        use_year_trend: bool = True, use_anomaly: bool = True,
                                        detrend_target: bool = True, static_features: list = None) -> pd.DataFrame:
    """static_features (e.g. soil) are constant per county across years, so an
    "anomaly" for them is degenerate (~0 + floating point noise) -- skip the
    anomaly transform for those and just pass them through as raw levels."""
    static_features = static_features or []
    dynamic_features = [c for c in base_features if c not in static_features]

    results = []
    for test_year in sorted(df["year"].unique()):
        train = df[df["year"] != test_year].copy()
        test = df[df["year"] == test_year].copy()

        features = list(base_features)

        if use_anomaly:
            county_means = county_feature_means(train, dynamic_features)
            train = add_anomaly_features(train, county_means, dynamic_features)
            test = add_anomaly_features(test, county_means, dynamic_features)
            features += [f"anom_{c}" for c in dynamic_features]

        if use_year_trend:
            train["year_trend"] = train["year"] - train["year"].min()
            test["year_trend"] = test["year"] - train["year"].min()
            features.append("year_trend")

        if detrend_target:
            trends = fit_county_trends(train)
            train_trend_pred = trend_predict(train, trends)
            test_trend_pred = trend_predict(test, trends)
            train_target = train[TARGET] - train_trend_pred
        else:
            test_trend_pred = np.zeros(len(test))
            train_target = train[TARGET]

        model = model_factory()
        model.fit(train[features], train_target)
        raw_preds = model.predict(test[features])
        preds = raw_preds + test_trend_pred  # add county trend back to get yield-scale prediction

        mae = mean_absolute_error(test[TARGET], preds)
        r2 = r2_score(test[TARGET], preds)
        results.append({"held_out_year": test_year, "mae": mae, "r2": r2, "n_test": len(test)})
    return pd.DataFrame(results)


def best_variant(crop: str, checkpoint_name: str) -> str:
    """"engineered" or "baseline" for GradientBoosting (the production
    model), from the saved comparison. Data-driven per crop/checkpoint, not
    a hardcoded assumption -- but MAE alone isn't a safe tiebreaker on its
    own: wheat/pre_harvest is a real case where engineered wins mean_mae by
    ~1.6% while its median R^2 goes NEGATIVE (worse than always predicting
    the mean) and baseline's stays positive (0.14) -- shipping "slightly
    lower average error but not actually tracking the signal" over a
    genuinely-working simpler alternative is the wrong call. corn/pre_harvest
    has a similar-looking R^2 dip for engineered (0.746 vs 0.747) but it's
    noise-level, both comfortably positive, so MAE should still decide there.
    The rule: prefer lower mean_mae, UNLESS that would ship a
    worse-than-useless (R^2 < 0) model while the other variant is genuinely
    useful (R^2 >= 0) -- only then does R^2 override MAE.
    """
    comparison = pd.read_csv("data/processed/feature_engineering_comparison.csv")
    rows = comparison[
        (comparison["crop"] == crop) & (comparison["checkpoint"] == checkpoint_name)
        & (comparison["model"] == "GradientBoosting")
    ]
    eng = rows[rows["variant"] == "engineered"].iloc[0]
    base = rows[rows["variant"] == "baseline"].iloc[0]

    if eng["median_r2"] < 0 and base["median_r2"] >= 0:
        return "baseline"
    if base["median_r2"] < 0 and eng["median_r2"] >= 0:
        return "engineered"
    return "engineered" if eng["mean_mae"] <= base["mean_mae"] else "baseline"


def compare_baseline_vs_engineered(df: pd.DataFrame, checkpoint_name: str) -> pd.DataFrame:
    from model_utils import prep_features, leave_one_year_out_eval

    rows = []
    df_prepped, features_baseline = prep_features(df)
    base_numeric = numeric_feature_cols(df)

    for model_name in ["RandomForest", "GradientBoosting", "MLP (small NN)"]:
        factory = MODELS[model_name]

        baseline = leave_one_year_out_eval(df_prepped, features_baseline, factory)
        rows.append({
            "checkpoint": checkpoint_name, "model": model_name, "variant": "baseline",
            "mean_mae": baseline["mae"].mean(), "median_r2": baseline["r2"].median(),
        })

        engineered = leave_one_year_out_eval_engineered(df_prepped, base_numeric, factory,
                                                         static_features=STATIC_COLS)
        rows.append({
            "checkpoint": checkpoint_name, "model": model_name, "variant": "engineered",
            "mean_mae": engineered["mae"].mean(), "median_r2": engineered["r2"].median(),
        })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    import sys
    from config import CROPS, crop_checkpoints
    from model_utils import load_checkpoint_table

    crops = sys.argv[1:] or list(CROPS.keys())
    all_rows = []
    for crop in crops:
        for checkpoint_name in crop_checkpoints(crop):
            df = load_checkpoint_table(checkpoint_name, crop)
            if (crop, checkpoint_name) not in NEEDS_STRESS:
                # Stress columns are merged into every checkpoint table by
                # build_dataset.py, but only NEEDS_STRESS checkpoints are
                # actually trained on them (see train_final_models.py) --
                # this comparison must match, or best_variant()/
                # load_confidence_mae() in predict_live.py would report
                # accuracy for a feature set nothing actually ships with.
                df = df.drop(columns=stress_columns(df))
            result = compare_baseline_vs_engineered(df, checkpoint_name)
            result.insert(0, "crop", crop)
            all_rows.append(result)
            print(f"\n=== {crop} / {checkpoint_name} ===")
            print(result.to_string(index=False))

    summary = pd.concat(all_rows, ignore_index=True)

    # Merge with any existing rows for crops NOT in this run, rather than
    # overwriting -- a partial run (e.g. `feature_engineering.py wheat`)
    # would otherwise silently wipe out corn/soybean's rows, which
    # predict_live.py's load_confidence_mae() depends on for every crop,
    # not just the one just re-run.
    out_path = "data/processed/feature_engineering_comparison.csv"
    try:
        existing = pd.read_csv(out_path)
        existing = existing[~existing["crop"].isin(crops)]
        summary = pd.concat([existing, summary], ignore_index=True)
    except FileNotFoundError:
        pass

    summary.to_csv(out_path, index=False)
    print(f"\nSaved {out_path} ({sorted(summary['crop'].unique())})")
