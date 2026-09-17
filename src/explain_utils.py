"""Shared SHAP-explanation helpers for api/routers/explain.py (county,
GET /predictions/explain) and field_advice.py (field, part of Layer 3 --
see ARCHITECTURE.md "Layer 3 -- Advice, sourced not invented"). Both explain
a trained tree model's prediction for one feature row using real per-instance
SHAP values, and both need the same human-readable feature labels, so the
labeling and SHAP-computation logic live here once rather than twice.
"""
import re

import numpy as np
import shap

MONTH_LABELS = {"jun": "June", "jul": "July", "aug": "August"}
STATE_NAMES = {"IA": "Iowa", "IL": "Illinois", "NE": "Nebraska", "NC": "North Carolina"}

BASE_LABELS = {
    "ndvi": "Vegetation greenness (NDVI)",
    "precip_sum": "Total rainfall",
    "tmean": "Average temperature",
    "tmax": "Peak temperature",
    "tmin": "Overnight low temperature",
    "soil_moisture": "Soil moisture",
    "edd_29c": "Extreme heat (degree-days above 29C)",
    "gdd_10_30c": "Beneficial heat accumulation",
    "days_above_30c": "Days above 30C",
    "days_above_35c": "Days above 35C",
    "dry_days": "Dry days (<1mm rain)",
    "heavy_rain_days": "Heavy rain days (>25mm)",
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


def shap_contributions(row, feature_cols: list, model, top_n: int = 8):
    """row: a pandas Series for one instance, already containing every column
    in feature_cols. Returns (top_contributions, other_contribution_bu_acre,
    other_feature_count, base_value_bu_acre) -- the pieces both callers
    assemble into their own response shape."""
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(row[feature_cols].to_frame().T)[0]
    # expected_value comes back as a length-1 array for this shap/sklearn
    # combination, not a bare scalar, even for a single-output regressor.
    base_value = float(np.ravel(explainer.expected_value)[0])

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
    other_count = max(0, len(contributions) - top_n)
    return top, other_sum, other_count, base_value
