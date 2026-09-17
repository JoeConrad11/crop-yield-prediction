"""GET /predictions/explain -- "why this prediction" breakdown for one
county's live prediction, using real per-instance SHAP values (not just
global feature importance) against the exact feature row predict_live.py
used (see the live_features_<crop>_<checkpoint>.csv snapshot it writes).

SHAP values are computed on-demand here (fast -- milliseconds, since it's
just running the already-trained tree model's explainer against a single
row) rather than at prediction time, keeping predict_live.py's live GEE
fetch path unchanged.
"""
from pathlib import Path

import joblib
import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from explain_utils import shap_contributions

router = APIRouter()

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
MODELS_DIR = Path(__file__).resolve().parents[2] / "models"


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
    trend_pred = float(row["trend_pred"])

    top, other_sum, other_count, base_value = shap_contributions(row, feature_cols, model, top_n)
    predicted_yield = base_value + sum(c["shap_value_bu_acre"] for c in top) + other_sum + trend_pred

    return {
        "predicted_yield_bu_acre": predicted_yield,
        "base_value_bu_acre": base_value,
        "trend_contribution_bu_acre": trend_pred,
        "top_contributions": top,
        "other_contribution_bu_acre": other_sum,
        "other_feature_count": other_count,
    }
