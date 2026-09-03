"""GET /predictions/explain -- "why this prediction" breakdown for one
county's live prediction, using real per-instance SHAP values (not just
global feature importance) against the exact feature row predict_live.py
used (see the live_features_<crop>_<checkpoint>.csv snapshot it writes).

SHAP values are computed on-demand here (fast -- milliseconds, since it's
just running the already-trained tree model's explainer against a single
row) rather than at prediction time, keeping predict_live.py's live GEE
fetch path unchanged.
"""
import re
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import shap
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
MODELS_DIR = Path(__file__).resolve().parents[2] / "models"

MONTH_LABELS = {"jun": "June", "jul": "July", "aug": "August"}
STATE_NAMES = {"IA": "Iowa", "IL": "Illinois", "NE": "Nebraska", "NC": "North Carolina"}

BASE_LABELS = {
    "ndvi": "Vegetation greenness (NDVI)",
    "precip_sum": "Total rainfall",
    "tmean": "Average temperature",
    "tmax": "Peak temperature",
    "tmin": "Overnight low temperature",
    "soil_moisture": "Soil moisture",
}
STATIC_LABELS = {
    "soil_organic_carbon": "Soil organic carbon",
    "soil_ph": "Soil pH",
    "soil_clay_pct": "Soil clay content",
    "soil_sand_pct": "Soil sand content",
    "soil_water_content_33kpa": "Soil water-holding capacity",
    "elevation_m": "Elevation",
    "slope_deg": "Terrain slope",
    "pct_continuous": "Continuous cropping (same crop as last year)",
    "year_trend": "Years since this county's trend baseline",
    "state_fips": "State (regional code)",
}


def humanize(feature: str) -> str:
    if feature.startswith("state_") and feature != "state_fips":
        alpha = feature.removeprefix("state_")
        return f"State: {STATE_NAMES.get(alpha, alpha)}"

    is_anomaly = feature.startswith("anom_")
    base = feature.removeprefix("anom_") if is_anomaly else feature

    month_match = re.match(r"(.+)_(jun|jul|aug)$", base)
    if month_match:
        stem, month = month_match.groups()
        label = f"{BASE_LABELS.get(stem, stem)} in {MONTH_LABELS[month]}"
    elif base in STATIC_LABELS:
        label = STATIC_LABELS[base]
    else:
        label = base.replace("_", " ").capitalize()

    return f"{label} vs. this county's average" if is_anomaly else label


@router.get("/predictions/explain")
def explain_prediction(
    crop: str = Query(...),
    state: str = Query(..., description="2-digit state FIPS"),
    county: str = Query(..., description="3-digit county FIPS"),
    checkpoint: str = Query("pre_harvest"),
    top_n: int = Query(8, ge=1, le=30),
):
    features_path = DATA_DIR / f"live_features_{crop}_{checkpoint}.csv"
    model_path = MODELS_DIR / f"gb_{crop}_{checkpoint}.joblib"
    if not features_path.exists() or not model_path.exists():
        raise HTTPException(status_code=404, detail="No live feature snapshot for this crop/checkpoint yet")

    df = pd.read_csv(features_path)
    df["state_fips"] = df["state_fips"].astype(str).str.zfill(2)
    df["county_fips"] = df["county_fips"].astype(str).str.zfill(3)
    row = df[(df["state_fips"] == state) & (df["county_fips"] == county)]
    if row.empty:
        raise HTTPException(status_code=404, detail="No live prediction for this county yet")
    row = row.iloc[0]

    feature_cols = [c for c in df.columns if c not in ("state_fips", "county_fips", "trend_pred")]
    model = joblib.load(model_path)

    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(row[feature_cols].to_frame().T)[0]
    # expected_value comes back as a length-1 array for this shap/sklearn
    # combination, not a bare scalar, even for a single-output regressor.
    base_value = float(np.ravel(explainer.expected_value)[0])
    trend_pred = float(row["trend_pred"])

    contributions = sorted(
        (
            {
                "feature": f,
                "label": humanize(f),
                "value": float(row[f]),
                "shap_value_bu_acre": float(v),
            }
            for f, v in zip(feature_cols, shap_values)
        ),
        key=lambda c: abs(c["shap_value_bu_acre"]),
        reverse=True,
    )

    top = contributions[:top_n]
    other_sum = sum(c["shap_value_bu_acre"] for c in contributions[top_n:])
    predicted_yield = base_value + sum(c["shap_value_bu_acre"] for c in contributions) + trend_pred

    return {
        "predicted_yield_bu_acre": predicted_yield,
        "base_value_bu_acre": base_value,
        "trend_contribution_bu_acre": trend_pred,
        "top_contributions": top,
        "other_contribution_bu_acre": other_sum,
        "other_feature_count": max(0, len(contributions) - top_n),
    }
