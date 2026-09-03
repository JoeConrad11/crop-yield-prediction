"""Live, in-season crop yield prediction: pulls whatever NDVI/weather/soil-
moisture data has actually accumulated for the CURRENT growing season as of
today (or a given date), and predicts yield using the persisted model that
matches how much of the season has elapsed.

Key differences from the historical pipeline:
- Uses the current year's data, not 2010-2023.
- CDL (Cropland Data Layer) isn't published for the current year until after
  harvest, so the crop mask falls back to the most recent available CDL year.
- Picks whichever checkpoint model (early_season / pre_harvest) matches how
  many growing-season months have actually completed -- a query in June only
  has June's data, so it can't use the pre_harvest model.
- Weather/soil/terrain/soil-moisture are crop-agnostic and only fetched once
  per run even when predicting multiple crops; only NDVI (crop-masked) needs
  a separate pull per crop.
"""
import json
import sys
from datetime import date

import ee
import joblib
import pandas as pd
from dotenv import load_dotenv
import os

from config import STATE_FIPS, PERIODS, CHECKPOINTS, CROPS, STATES, crop_state_fips
from fetch_gee import fetch_period_ndvi
from fetch_prism import fetch_period_weather
from fetch_soil_moisture import fetch_period_soil_moisture
from fetch_rotation import fetch_rotation_signal
from build_dataset import SOIL_COLS, TERRAIN_COLS, MIN_CROP_PIXELS
from feature_engineering import trend_predict, add_anomaly_features, best_variant

from gee_auth import ensure_initialized
ensure_initialized()


def completed_periods(as_of: date) -> list:
    """Which growing-season periods (jun/jul/aug) have fully elapsed as of this date."""
    done = []
    for period_name, (start_md, end_md) in PERIODS.items():
        end_month, end_day = map(int, end_md.split("-"))
        period_end = date(as_of.year, end_month, end_day)
        if as_of > period_end:
            done.append(period_name)
    return done


def pick_checkpoint(done_periods: list) -> str:
    for checkpoint_name, periods in sorted(CHECKPOINTS.items(), key=lambda kv: -len(kv[1])):
        if set(periods).issubset(set(done_periods)):
            return checkpoint_name
    return None


def latest_available_cdl_year() -> int:
    cdl = ee.ImageCollection("USDA/NASS/CDL")
    latest = cdl.sort("system:time_start", False).first()
    return int(ee.Date(latest.get("system:time_start")).format("YYYY").getInfo())


def fetch_current_weather_and_moisture(current_year: int, periods: list) -> pd.DataFrame:
    """Crop-agnostic -- fetched once regardless of how many crops are being predicted."""
    weather_frames, moisture_frames = [], []
    for period_name in periods:
        start_md, end_md = PERIODS[period_name]
        weather_frames.append(fetch_period_weather(STATE_FIPS, current_year, current_year,
                                                     period_name, start_md, end_md))
        moisture_frames.append(fetch_period_soil_moisture(STATE_FIPS, current_year, current_year,
                                                            period_name, start_md, end_md))
    weather = pd.concat(weather_frames, ignore_index=True)
    moisture = pd.concat(moisture_frames, ignore_index=True)

    keys = ["year", "state_fips", "county_fips", "county_name"]
    weather_wide = weather.pivot(index=keys, columns="period",
                                  values=["precip_sum_mm", "tmean_c", "tmax_c", "tmin_c"])
    weather_wide.columns = [f"{val.replace('_mm', '').replace('_c', '')}_{p}" for val, p in weather_wide.columns]

    moisture_wide = moisture.pivot(index=keys, columns="period", values="soil_moisture_vol")
    moisture_wide.columns = [f"soil_moisture_{p}" for p in moisture_wide.columns]

    combined = weather_wide.join(moisture_wide).reset_index()
    combined["state_fips"] = combined["state_fips"].astype(str).str.zfill(2)
    combined["county_fips"] = combined["county_fips"].astype(str).str.zfill(3)
    return combined


def fetch_current_ndvi(current_year: int, periods: list, cdl_code: int, cdl_year: int,
                        state_fips_list: list = STATE_FIPS) -> pd.DataFrame:
    frames = []
    for period_name in periods:
        start_md, end_md = PERIODS[period_name]
        frames.append(fetch_period_ndvi(state_fips_list, current_year, current_year,
                                         period_name, start_md, end_md, cdl_code, cdl_year=cdl_year))
    ndvi = pd.concat(frames, ignore_index=True)

    keys = ["year", "state_fips", "county_fips", "county_name"]
    ndvi_wide = ndvi.pivot(index=keys, columns="period", values=["ndvi_mean", "crop_pixel_count"])
    ndvi_wide.columns = [f"{'ndvi' if val == 'ndvi_mean' else 'crop_pixels'}_{p}"
                          for val, p in ndvi_wide.columns]
    ndvi_wide = ndvi_wide.reset_index()
    ndvi_wide["state_fips"] = ndvi_wide["state_fips"].astype(str).str.zfill(2)
    ndvi_wide["county_fips"] = ndvi_wide["county_fips"].astype(str).str.zfill(3)

    pixel_cols = [f"crop_pixels_{p}" for p in periods]
    for col in pixel_cols:
        ndvi_wide = ndvi_wide[ndvi_wide[col] >= MIN_CROP_PIXELS]
    # keep the weakest-link pixel count as a coverage/confidence signal instead
    # of dropping it entirely -- a county just above MIN_CROP_PIXELS is far
    # noisier than one with 10x the coverage, even though both pass the filter
    ndvi_wide["crop_pixel_coverage"] = ndvi_wide[pixel_cols].min(axis=1)
    return ndvi_wide.drop(columns=pixel_cols).reset_index(drop=True)


def fetch_current_rotation(cdl_code: int, cdl_year: int, state_fips_list: list = STATE_FIPS) -> pd.DataFrame:
    """Rotation signal for the CURRENT season uses the same cdl_year proxy as
    the NDVI crop mask (real CDL for the current year isn't published yet):
    of the pixels classified as this crop in the proxy year, what fraction
    were also this crop the year before that. Crop-specific like NDVI, not
    shared like weather/soil."""
    df = fetch_rotation_signal(state_fips_list, cdl_year, cdl_year, cdl_code)
    df["state_fips"] = df["state_fips"].astype(str).str.zfill(2)
    df["county_fips"] = df["county_fips"].astype(str).str.zfill(3)
    return df[["state_fips", "county_fips", "pct_continuous"]]


def attach_static_features(df: pd.DataFrame) -> pd.DataFrame:
    soil = pd.read_csv("data/raw/soil_properties.csv")
    terrain = pd.read_csv("data/raw/terrain_properties.csv")
    for static_df in (soil, terrain):
        static_df["state_fips"] = static_df["state_fips"].astype(str).str.zfill(2)
        static_df["county_fips"] = static_df["county_fips"].astype(str).str.zfill(3)
    df = df.merge(soil[["state_fips", "county_fips"] + SOIL_COLS], on=["state_fips", "county_fips"], how="inner")
    df = df.merge(terrain[["state_fips", "county_fips"] + TERRAIN_COLS], on=["state_fips", "county_fips"], how="inner")
    return df


def load_confidence_mae(crop: str, checkpoint_name: str) -> float:
    """Typical model error (bu/acre), from the SAME variant (engineered or
    baseline, see feature_engineering.best_variant) actually shipped for this
    crop/checkpoint -- used as an honest error margin so predictions aren't
    shown as falsely precise point estimates. Not a proper prediction
    interval (that would need quantile regression), just the model's known
    average miss. Was previously hardcoded to always read the "engineered"
    row, which understated wheat/pre_harvest's real error since that one
    actually ships on "baseline"."""
    comparison = pd.read_csv("data/processed/feature_engineering_comparison.csv")
    variant = best_variant(crop, checkpoint_name)
    row = comparison[(comparison["crop"] == crop) & (comparison["checkpoint"] == checkpoint_name) &
                      (comparison["model"] == "GradientBoosting") & (comparison["variant"] == variant)]
    return row["mean_mae"].iloc[0]


def coverage_tier(pixel_count: int) -> str:
    """Rough confidence label from how much crop-classified area backs the
    NDVI signal for a county -- a county barely above MIN_CROP_PIXELS is
    much noisier than one with 10x the coverage, even though both pass the
    filter in fetch_current_ndvi."""
    if pixel_count >= MIN_CROP_PIXELS * 10:
        return "high"
    if pixel_count >= MIN_CROP_PIXELS * 3:
        return "medium"
    return "low"


def add_historical_comparison(df: pd.DataFrame, crop: str) -> pd.DataFrame:
    historical = pd.read_csv(f"data/processed/model_table_{crop}_pre_harvest.csv")
    historical["state_fips"] = historical["state_fips"].astype(str).str.zfill(2)
    historical["county_fips"] = historical["county_fips"].astype(str).str.zfill(3)
    hist_mean = historical.groupby(["state_fips", "county_fips"])["yield_bu_acre"] \
        .mean().rename("historical_avg_yield").reset_index()
    df = df.merge(hist_mean, on=["state_fips", "county_fips"], how="left")
    df["delta_vs_historical"] = df["predicted_yield_bu_acre"] - df["historical_avg_yield"]
    df["pct_vs_historical"] = 100 * df["delta_vs_historical"] / df["historical_avg_yield"]
    return df


def predict(crop: str = "corn", as_of: date = None,
            weather_moisture_cache: pd.DataFrame = None, cdl_year: int = None) -> pd.DataFrame:
    as_of = as_of or date.today()
    done = completed_periods(as_of)
    checkpoint_name = pick_checkpoint(done)

    if checkpoint_name is None:
        print(f"As of {as_of}, only {done or 'no'} periods are complete -- "
              f"no checkpoint model covers this little of the season yet.")
        sys.exit(1)

    periods = CHECKPOINTS[checkpoint_name]
    print(f"[{crop}] As of {as_of}: periods {periods} complete -> using '{checkpoint_name}' model")

    cdl_year = cdl_year or latest_available_cdl_year()
    if cdl_year < as_of.year:
        print(f"Note: {as_of.year} Cropland Data Layer not yet published -- "
              f"using {cdl_year} CDL as the {crop} mask proxy.")

    ndvi = fetch_current_ndvi(as_of.year, periods, CROPS[crop]["cdl_code"], cdl_year, crop_state_fips(crop))
    weather_moisture = weather_moisture_cache
    if weather_moisture is None:
        weather_moisture = fetch_current_weather_and_moisture(as_of.year, periods)
    rotation = fetch_current_rotation(CROPS[crop]["cdl_code"], cdl_year, crop_state_fips(crop))

    current = ndvi.merge(weather_moisture, on=["year", "state_fips", "county_fips", "county_name"], how="inner")
    current = current.merge(rotation, on=["state_fips", "county_fips"], how="inner")
    current = attach_static_features(current)

    with open(f"models/gb_{crop}_{checkpoint_name}_features.json") as f:
        features = json.load(f)
    model = joblib.load(f"models/gb_{crop}_{checkpoint_name}.joblib")
    aux = joblib.load(f"models/gb_{crop}_{checkpoint_name}_aux.joblib")

    state_map = {v: k for k, v in STATES.items()}
    current["state_alpha"] = current["state_fips"].map(state_map)
    current = pd.get_dummies(current, columns=["state_alpha"], prefix="state")

    # Apply the same transform train_final_models.py used for THIS crop --
    # engineered (NDVI/weather anomalies + county-trend detrending) proved
    # out for corn/soybean but hurt wheat's smaller dataset, so which one
    # was actually used is data-driven per crop/checkpoint (see aux["variant"],
    # written by train_final_models.py via feature_engineering.best_variant).
    if aux["variant"] == "engineered":
        current = add_anomaly_features(current, aux["county_means"], aux["dynamic_features"])
        current["year_trend"] = as_of.year - aux["min_year"]
        trend_pred = trend_predict(current, aux["trends"])
    else:
        trend_pred = 0.0

    for col in features:
        if col not in current.columns:
            current[col] = 0  # state dummy not present in this batch

    current["predicted_yield_bu_acre"] = model.predict(current[features]) + trend_pred
    current = add_historical_comparison(current, crop)
    current.insert(0, "crop", crop)

    # Snapshot of the exact feature row + trend contribution used for each
    # county's prediction -- lets the "why this prediction" explain endpoint
    # (api/routers/explain.py) compute real SHAP values without needing a
    # live GEE re-fetch. Overwritten each run (latest snapshot only, no
    # date in the filename) since the explanation only needs to match
    # whatever's currently live in live_predictions.
    feature_snapshot = current[["state_fips", "county_fips"] + features].copy()
    feature_snapshot["trend_pred"] = trend_pred
    feature_snapshot.to_csv(f"data/processed/live_features_{crop}_{checkpoint_name}.csv", index=False)

    # uncertainty: honest error margin (model's typical CV miss) + a coverage
    # confidence tier, so predictions aren't displayed as falsely precise
    confidence_mae = load_confidence_mae(crop, checkpoint_name)
    current["predicted_yield_low"] = current["predicted_yield_bu_acre"] - confidence_mae
    current["predicted_yield_high"] = current["predicted_yield_bu_acre"] + confidence_mae
    current["confidence_mae"] = confidence_mae
    current["coverage_tier"] = current["crop_pixel_coverage"].apply(coverage_tier)

    out_cols = ["crop", "year", "state_fips", "county_fips", "county_name",
                "predicted_yield_bu_acre", "predicted_yield_low", "predicted_yield_high", "confidence_mae",
                "coverage_tier", "crop_pixel_coverage",
                "historical_avg_yield", "delta_vs_historical", "pct_vs_historical"]
    result = current[out_cols].sort_values("pct_vs_historical")

    out_path = f"data/processed/live_prediction_{crop}_{as_of.isoformat()}.csv"
    result.to_csv(out_path, index=False)
    print(f"Saved {len(result)} county predictions to {out_path}\n")
    return result


if __name__ == "__main__":
    crops = sys.argv[1:] or list(CROPS.keys())
    as_of = date.today()

    # weather/soil-moisture are crop-agnostic -- fetch once, reuse for every crop
    done = completed_periods(as_of)
    checkpoint_name = pick_checkpoint(done)
    periods = CHECKPOINTS[checkpoint_name] if checkpoint_name else []
    weather_moisture_cache = fetch_current_weather_and_moisture(as_of.year, periods) if periods else None
    cdl_year = latest_available_cdl_year()

    results = []
    for crop in crops:
        results.append(predict(crop, as_of, weather_moisture_cache, cdl_year))

    combined = pd.concat(results, ignore_index=True)
    print(combined.sort_values(["county_name", "crop"]).to_string(index=False))
