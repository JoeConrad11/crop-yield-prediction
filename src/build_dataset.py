"""Merge NASS yield labels + GEE NDVI (crop-masked) + PRISM weather into
model-ready tables, one per crop per season checkpoint, keyed on
(state_fips, county_fips, year).

NDVI and weather are fetched per growing-season month (period) and pivoted
wide here (e.g. ndvi_jun, ndvi_jul, ndvi_aug, precip_jun, ...) so each
checkpoint's table only exposes the periods that would actually be known at
that point in the season.

Weather, soil, terrain, and soil moisture are crop-agnostic (same physical
county properties regardless of what's planted) and are fetched once, not
per crop. Only yield labels and NDVI are crop-specific.
"""
import os

import pandas as pd

from config import STATES, CROPS, crop_checkpoints

ID_COLS = ["year", "state_fips", "state_alpha", "county_fips", "county_name"]
MIN_CROP_PIXELS = 500
SOIL_COLS = ["soil_organic_carbon", "soil_ph", "soil_clay_pct", "soil_sand_pct", "soil_water_content_33kpa"]
TERRAIN_COLS = ["elevation_m", "slope_deg"]


def load_yield(crop: str) -> pd.DataFrame:
    df = pd.read_csv(f"data/raw/nass_{crop}_yield_multistate.csv")
    df = df[df["short_desc"] == CROPS[crop]["yield_label"]].copy()
    df["state_fips"] = df["state_alpha"].map(STATES)
    df["county_fips"] = df["county_code"].astype(int).map(lambda x: f"{x:03d}")
    return df[["year", "state_fips", "state_alpha", "county_fips", "county_name", "Value"]] \
        .rename(columns={"Value": "yield_bu_acre"})


def load_ndvi_wide(crop: str) -> pd.DataFrame:
    """Long (year, county, period) -> wide (one ndvi_<period> + crop_pixels_<period> column per period)."""
    df = pd.read_csv(f"data/raw/gee_ndvi_{crop}_periods.csv")
    df["state_fips"] = df["state_fips"].astype(str).str.zfill(2)
    df["county_fips"] = df["county_fips"].astype(str).str.zfill(3)
    keys = ["year", "state_fips", "county_fips"]
    wide = df.pivot(index=keys, columns="period", values=["ndvi_mean", "crop_pixel_count"])
    wide.columns = [f"{'ndvi' if val == 'ndvi_mean' else 'crop_pixels'}_{period}"
                    for val, period in wide.columns]
    return wide.reset_index()


def load_weather_wide() -> pd.DataFrame:
    df = pd.read_csv("data/raw/prism_weather_periods.csv")
    df["state_fips"] = df["state_fips"].astype(str).str.zfill(2)
    df["county_fips"] = df["county_fips"].astype(str).str.zfill(3)
    keys = ["year", "state_fips", "county_fips"]
    wide = df.pivot(index=keys, columns="period", values=["precip_sum_mm", "tmean_c", "tmax_c", "tmin_c"])
    wide.columns = [f"{val.replace('_mm', '').replace('_c', '')}_{period}" for val, period in wide.columns]
    return wide.reset_index()


NEEDS_STRESS = {("corn", "early_season"), ("soybeans", "pre_harvest")}
"""Which (crop, checkpoint) combos ship Layer 2 stress features. Decided by
evaluate_stress_features.py's leave-one-year-out comparison: a real,
non-noise improvement showed up only here; everywhere else it was a wash
or (wheat, both checkpoints) actively worse or untrustworthy on wheat's
tiny sample, consistent with the dormancy caveat in growth_stages.py.
Read by train_final_models.py (which features to train on) AND the live
fetchers (predict_live.py, fetch_field_features.py), which must fetch
these columns for exactly the checkpoints trained on them -- never
silently zero-fill a stress feature the model expects."""

STRESS_METRICS = ["edd_29c", "gdd_10_30c", "days_above_30c", "days_above_35c",
                   "dry_days", "heavy_rain_days"]


def stress_columns(df: pd.DataFrame) -> list:
    """Which of df's columns are Layer 2 stress features (any period).
    Single shared definition -- evaluate_stress_features.py, train_final_models.py,
    and feature_engineering.py all need to drop/keep the exact same set, and
    a copy that drifts is how a checkpoint ends up trained on columns the
    evaluation gate never actually tested."""
    return [c for c in df.columns if any(c.startswith(m + "_") for m in STRESS_METRICS)]


def load_stress_wide() -> pd.DataFrame:
    """Agronomy Layer 2 threshold metrics (see fetch_prism.fetch_period_stress
    and ARCHITECTURE.md). Optional: returns None when the file hasn't been
    fetched, so the pipeline still builds without it and the before/after
    comparison stays runnable in both directions."""
    path = "data/raw/prism_stress_periods.csv"
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    df["state_fips"] = df["state_fips"].astype(str).str.zfill(2)
    df["county_fips"] = df["county_fips"].astype(str).str.zfill(3)
    keys = ["year", "state_fips", "county_fips"]
    wide = df.pivot(index=keys, columns="period", values=STRESS_METRICS)
    wide.columns = [f"{metric}_{period}" for metric, period in wide.columns]
    return wide.reset_index()


def load_soil() -> pd.DataFrame:
    """Static per-county soil properties (no year dimension)."""
    df = pd.read_csv("data/raw/soil_properties.csv")
    df["state_fips"] = df["state_fips"].astype(str).str.zfill(2)
    df["county_fips"] = df["county_fips"].astype(str).str.zfill(3)
    return df[["state_fips", "county_fips"] + SOIL_COLS]


def load_terrain() -> pd.DataFrame:
    """Static per-county terrain (no year dimension)."""
    df = pd.read_csv("data/raw/terrain_properties.csv")
    df["state_fips"] = df["state_fips"].astype(str).str.zfill(2)
    df["county_fips"] = df["county_fips"].astype(str).str.zfill(3)
    return df[["state_fips", "county_fips"] + TERRAIN_COLS]


def load_soil_moisture_wide() -> pd.DataFrame:
    df = pd.read_csv("data/raw/soil_moisture_periods.csv")
    df["state_fips"] = df["state_fips"].astype(str).str.zfill(2)
    df["county_fips"] = df["county_fips"].astype(str).str.zfill(3)
    keys = ["year", "state_fips", "county_fips"]
    wide = df.pivot(index=keys, columns="period", values="soil_moisture_vol")
    wide.columns = [f"soil_moisture_{period}" for period in wide.columns]
    return wide.reset_index()


def load_rotation(crop: str) -> pd.DataFrame:
    """pct_continuous: fraction of this year's crop-masked pixels that were the
    same crop last year too (built from CDL year-over-year, see fetch_rotation.py).
    Not period-specific -- known once the crop mask is known, same as NDVI's mask."""
    df = pd.read_csv(f"data/raw/rotation_{crop}.csv")
    df["state_fips"] = df["state_fips"].astype(str).str.zfill(2)
    df["county_fips"] = df["county_fips"].astype(str).str.zfill(3)
    return df[["year", "state_fips", "county_fips", "pct_continuous"]]


def build_full_table(crop: str) -> pd.DataFrame:
    """All periods merged together; checkpoint-specific tables are sliced from this."""
    yield_df = load_yield(crop)
    ndvi_df = load_ndvi_wide(crop)
    weather_df = load_weather_wide()
    soil_df = load_soil()
    terrain_df = load_terrain()
    soil_moisture_df = load_soil_moisture_wide()
    rotation_df = load_rotation(crop)

    keys = ["year", "state_fips", "county_fips"]
    merged = yield_df.merge(ndvi_df, on=keys, how="inner")
    merged = merged.merge(weather_df, on=keys, how="inner")
    merged = merged.merge(soil_moisture_df, on=keys, how="inner")
    merged = merged.merge(rotation_df, on=keys, how="inner")
    merged = merged.merge(soil_df, on=["state_fips", "county_fips"], how="inner")
    merged = merged.merge(terrain_df, on=["state_fips", "county_fips"], how="inner")

    # Layer 2 stress metrics, merged only if they've been fetched -- keeps
    # the table buildable (and the with/without comparison honest) either way.
    stress_df = load_stress_wide()
    if stress_df is not None:
        merged = merged.merge(stress_df, on=keys, how="inner")
    return merged


def build_checkpoint_table(full: pd.DataFrame, checkpoint_name: str, crop: str) -> pd.DataFrame:
    periods = crop_checkpoints(crop)[checkpoint_name]
    pixel_cols = [f"crop_pixels_{p}" for p in periods]
    feature_cols = (
        [f"ndvi_{p}" for p in periods]
        + [f"precip_sum_{p}" for p in periods]
        + [f"tmean_{p}" for p in periods]
        + [f"tmax_{p}" for p in periods]
        + [f"tmin_{p}" for p in periods]
        + [f"soil_moisture_{p}" for p in periods]
        + SOIL_COLS
        + TERRAIN_COLS
        + ["pct_continuous"]
    )
    # Layer 2 stress metrics, scoped to THIS checkpoint's periods like every
    # other period feature above -- an early_season model must not see
    # August heat that hasn't happened yet. Filtered against the table's
    # actual columns so the build still works before the stress pull exists.
    feature_cols += [c for c in (f"{metric}_{p}" for metric in STRESS_METRICS for p in periods)
                      if c in full.columns]
    df = full[ID_COLS + ["yield_bu_acre"] + feature_cols + pixel_cols].copy()
    # every visible period must have enough crop-classified area for NDVI to be meaningful
    for col in pixel_cols:
        df = df[df[col] >= MIN_CROP_PIXELS]
    return df.drop(columns=pixel_cols).reset_index(drop=True)


if __name__ == "__main__":
    import sys
    crops = sys.argv[1:] or list(CROPS.keys())
    for crop in crops:
        full = build_full_table(crop)
        for checkpoint_name in crop_checkpoints(crop):
            df = build_checkpoint_table(full, checkpoint_name, crop)
            out_path = f"data/processed/model_table_{crop}_{checkpoint_name}.csv"
            df.to_csv(out_path, index=False)
            print(f"[{crop}/{checkpoint_name}] Saved {len(df)} rows, {df['county_name'].nunique()} counties, "
                  f"{df['state_alpha'].nunique()} states, {df['year'].nunique()} years, "
                  f"{len(df.columns) - len(ID_COLS) - 1} features -> {out_path}")
            print(df.groupby("state_alpha")["yield_bu_acre"].agg(["count", "mean"]))
            print()
