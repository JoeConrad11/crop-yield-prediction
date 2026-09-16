"""Phase 3 of the farmer-app roadmap (see ../ARCHITECTURE.md): apply the
existing county-calibrated model to a single farmer-drawn field, using
fetch_field_features.py's field-level feature row plus its spatial-joined
state/county (field_county()) for the state one-hot encoding and the
historical-yield comparison -- the same two things predict_live.py needs
per county, just for one field instead of a whole state's worth of counties.

IMPORTANT HONEST CAVEAT (repeated from fetch_field_features.py and
ARCHITECTURE.md): there is no field-level yield ground truth to train on,
so this is field-level INPUT run through a COUNTY-calibrated MODEL, not a
field-level-trained model. Frame anything built on this as "vs. your
county's trend," never an exact bushels/acre guarantee.
"""
import json
from datetime import date

import joblib
import pandas as pd

from config import STATES, crop_state_alphas
from fetch_field_features import (
    fetch_field_features, field_coverage_tier, field_crop_composition,
    field_geometry_from_boundary, M2_PER_ACRE,
)
from predict_live import load_confidence_mae, add_historical_comparison
from feature_engineering import add_anomaly_features, trend_predict

STATE_ALPHA_BY_FIPS = {v: k for k, v in STATES.items()}

# Enough of the USDA CDL legend to explain a coverage failure in words a
# farmer recognises. Only the classes common in this project's states --
# anything else falls back to its raw code, which is still checkable
# against USDA's published legend.
CDL_CROP_NAMES = {
    1: "corn", 5: "soybeans", 24: "winter wheat", 4: "sorghum", 21: "barley",
    28: "oats", 36: "alfalfa", 37: "other hay", 43: "potatoes", 61: "fallow",
    111: "open water", 121: "developed", 122: "developed", 123: "developed",
    124: "developed", 131: "barren", 141: "deciduous forest", 142: "evergreen forest",
    143: "mixed forest", 152: "shrubland", 176: "grass/pasture", 190: "woody wetlands",
    195: "herbaceous wetlands",
}


def predict_field(boundary: dict, crop: str, as_of: date = None, field_id: str = None) -> dict:
    """Returns a dict shaped like one row of predict_live.predict()'s
    output. Meant to sit directly behind an API endpoint a farmer hits by
    clicking a button (see api/routers/field_predict.py) -- so failures
    come back as {"error": "<code>", "message": ...} instead of raising or
    sys.exit(1) the way the CLI-oriented predict_live.predict() does."""
    as_of = as_of or date.today()
    row = fetch_field_features(boundary, crop, as_of, field_id=field_id)
    if row is None:
        return {
            "error": "season_not_started",
            "message": "Not enough of this year's growing season has happened yet to make a prediction.",
        }

    state_alpha = STATE_ALPHA_BY_FIPS.get(row["state_fips"])
    if state_alpha not in crop_state_alphas(crop):
        where = row.get("county_name") or "an unrecognized location"
        if state_alpha:
            where += f", {state_alpha}"
        return {
            "error": "unsupported_region",
            "message": f"This field is in {where} -- the {crop} model hasn't been trained on this region yet.",
            "county_name": row.get("county_name"),
            "state_alpha": state_alpha,
        }

    tier = field_coverage_tier(row.get("crop_observed_acres"), row.get("field_acres"),
                                row.get("crop_pixel_scale_m"))
    if tier == "unreliable":
        # One pixel covers too much of this field for the reading to be
        # about the field rather than its surroundings (see
        # field_coverage_tier's docstring for the measured basis). A number
        # built on that isn't "low confidence," it's partly about different
        # land, so don't return one.
        pixel_acres = row["crop_pixel_scale_m"] ** 2 / M2_PER_ACRE
        return {
            "error": "unreliable_coverage",
            "message": f"This field is {row['field_acres']:.0f} acres, but today's satellite "
                       f"measures in {pixel_acres:.1f}-acre pixels -- a single pixel covers "
                       f"{100 * pixel_acres / row['field_acres']:.0f}% of your field and extends past "
                       f"its edges, so any number here would mostly describe your neighbors' ground, "
                       f"not yours. Your field's growth stage and season-over-season comparison "
                       f"don't have this limit and are shown above.",
            "crop_observed_acres": row["crop_observed_acres"],
            "field_acres": row["field_acres"],
        }

    checkpoint_name = row["checkpoint"]
    with open(f"models/gb_{crop}_{checkpoint_name}_features.json") as f:
        features = json.load(f)
    model = joblib.load(f"models/gb_{crop}_{checkpoint_name}.joblib")
    aux = joblib.load(f"models/gb_{crop}_{checkpoint_name}_aux.joblib")

    df = pd.DataFrame([row])
    df["state_alpha"] = state_alpha
    df = pd.get_dummies(df, columns=["state_alpha"], prefix="state")

    # Same variant switch predict_live.predict() uses (see aux["variant"],
    # written by train_final_models.py) -- county trend/anomaly machinery
    # works unchanged on a one-row df since it's keyed by (state_fips,
    # county_fips) per-row, and this field's real county is in that index.
    if aux["variant"] == "engineered":
        df = add_anomaly_features(df, aux["county_means"], aux["dynamic_features"])
        df["year_trend"] = as_of.year - aux["min_year"]
        trend_pred = trend_predict(df, aux["trends"])
    else:
        trend_pred = 0.0

    for col in features:
        if col not in df.columns:
            df[col] = 0  # a state dummy this field's state doesn't need, or a feature absent at field scale

    # A field this small can end up with literally zero CDL/MODIS pixels
    # classified as `crop` in the mask year -- e.g. it was actually the
    # OTHER crop in a corn/soy rotation that season -- which leaves
    # ndvi_*/pct_continuous as None (see fetch_period_ndvi_for_field /
    # fetch_field_rotation). GradientBoostingRegressor can't handle NaN
    # input, and a fabricated fallback value would be a silent wrong
    # answer, so surface this as a real, honest result instead of crashing.
    missing = df[features].columns[df[features].isna().any()].tolist()
    if missing:
        # Explain the failure with what the crop map actually shows on this
        # field, rather than the opaque "not enough crop detected" that sent
        # live testing into blind corn-then-soybeans guessing. The farmer's
        # own answer is authoritative here -- CDL is published ~a year late,
        # so on a rotated field it is describing LAST season, and a
        # disagreement is evidence of that staleness, not a correction to
        # the farmer (see src/supabase_farm_migration_planting.sql).
        composition = field_crop_composition(
            field_geometry_from_boundary(boundary), row["cdl_year"]
        )
        named = []
        for c in composition:
            if c["pct"] < 5:
                continue
            label = CDL_CROP_NAMES.get(c["cdl_code"], "CDL class {}".format(c["cdl_code"]))
            named.append("{} {:.0f}%".format(label, c["pct"]))
        detail = (
            f" The {row['cdl_year']} crop map for this field shows {', '.join(named)}."
            if named else ""
        )
        return {
            "error": "insufficient_coverage",
            "message": f"You told us this field is {crop}, but the satellite's crop map doesn't show "
                       f"enough {crop} here to measure it.{detail} That map is about a year behind, so "
                       f"on a field that rotates it's often describing last season -- your answer is "
                       f"what we'll trust, but we can't produce a reliable number for this season yet.",
            "missing_features": missing,
            "cdl_year": row["cdl_year"],
            "cdl_composition": composition,
        }

    df["predicted_yield_bu_acre"] = model.predict(df[features]) + trend_pred
    df = add_historical_comparison(df, crop)

    confidence_mae = load_confidence_mae(crop, checkpoint_name)
    predicted = float(df["predicted_yield_bu_acre"].iloc[0])
    historical_avg = df["historical_avg_yield"].iloc[0]
    delta = df["delta_vs_historical"].iloc[0]
    pct = df["pct_vs_historical"].iloc[0]

    return {
        "field_id": field_id,
        "crop": crop,
        "year": row["year"],
        "checkpoint": checkpoint_name,
        "state_fips": row["state_fips"],
        "county_fips": row["county_fips"],
        "county_name": row["county_name"],
        "predicted_yield_bu_acre": predicted,
        "predicted_yield_low": predicted - confidence_mae,
        "predicted_yield_high": predicted + confidence_mae,
        "confidence_mae": float(confidence_mae),
        "coverage_tier": tier,
        "crop_pixel_coverage": row["crop_pixel_coverage"],
        "crop_observed_acres": row["crop_observed_acres"],
        "field_acres": row["field_acres"],
        "historical_avg_yield": float(historical_avg) if pd.notna(historical_avg) else None,
        "delta_vs_historical": float(delta) if pd.notna(delta) else None,
        "pct_vs_historical": float(pct) if pd.notna(pct) else None,
    }


if __name__ == "__main__":
    import sys

    # Same ~40-acre demo polygon near Ames, IA as fetch_field_features.py's
    # own __main__, so this is runnable ad hoc without a real Supabase field.
    demo_boundary = {
        "type": "Polygon",
        "coordinates": [[
            [-93.62, 41.99], [-93.61, 41.99], [-93.61, 41.98], [-93.62, 41.98], [-93.62, 41.99],
        ]],
    }
    crop = sys.argv[1] if len(sys.argv) > 1 else "corn"
    print(f"Predicting for crop={crop}, demo polygon near Ames, IA...")
    result = predict_field(demo_boundary, crop)
    for key, value in result.items():
        print(f"  {key}: {value}")
