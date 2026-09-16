"""FastAPI service for the county-yield-anomaly pipeline (Assignment 4).

Run locally (from assignment4/): uvicorn serve:app --reload
Then open http://localhost:8000/docs
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from pipeline_def import CountyAnomalyTransformer  # noqa: F401 -- required to unpickle the bundle

ARTIFACT_PATH = Path(__file__).resolve().parent / "pipeline.joblib"

app = FastAPI(title="County Yield Anomaly Pipeline API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Loaded once at import time, not per-request.
_bundle = None
_load_error = None
try:
    _bundle = joblib.load(ARTIFACT_PATH)
except Exception as exc:  # noqa: BLE001 -- any load failure should degrade to 503, not crash the process
    _load_error = str(exc)


class PredictRequest(BaseModel):
    state_fips: int = Field(..., ge=1, le=56, description="US state FIPS code")
    county_fips: int = Field(..., ge=1, le=999, description="County FIPS code within the state")
    year: int = Field(..., ge=1990, le=2035)
    ndvi_jun: float = Field(..., ge=0.0, le=1.0, description="Mean NDVI, June")
    ndvi_jul: float = Field(..., ge=0.0, le=1.0, description="Mean NDVI, July")
    precip_sum_jun: float = Field(..., ge=0.0, le=2000.0, description="Total precipitation, June (mm)")
    precip_sum_jul: float = Field(..., ge=0.0, le=2000.0, description="Total precipitation, July (mm)")
    tmean_jun: float = Field(..., ge=-10.0, le=50.0, description="Mean temperature, June (C)")
    tmean_jul: float = Field(..., ge=-10.0, le=50.0, description="Mean temperature, July (C)")
    edd_29c_jul: float = Field(..., ge=0.0, le=500.0, description="Extreme degree days above 29C, July")
    dry_days_jul: float = Field(..., ge=0.0, le=31.0, description="Days with <1mm rain, July")
    soil_organic_carbon: float = Field(..., ge=0.0, le=200.0)
    soil_ph: float = Field(..., ge=3.0, le=10.0)
    elevation_m: float = Field(..., ge=-100.0, le=4500.0)
    slope_deg: float = Field(..., ge=0.0, le=45.0)


class PredictResponse(BaseModel):
    predicted_yield_bu_acre: float
    known_county: bool


def _ensure_loaded():
    if _bundle is None:
        raise HTTPException(status_code=503, detail=f"Pipeline artifact not loaded: {_load_error}")


@app.get("/health")
def health():
    return {"status": "ok" if _bundle is not None else "artifact_unavailable"}


@app.get("/info")
def info():
    """Describes the loaded artifact: pipeline steps, when it was built,
    the sklearn version it was fit with, and the features it expects."""
    _ensure_loaded()
    return {
        "metadata": _bundle["metadata"],
        "group_cols": _bundle["group_cols"],
        "value_cols": _bundle["value_cols"],
        "static_cols": _bundle["static_cols"],
        "target": _bundle["target"],
    }


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest):
    _ensure_loaded()
    row = pd.DataFrame([req.model_dump()])
    pipeline = _bundle["pipeline"]
    key = (req.state_fips, req.county_fips)
    known = pipeline.named_steps["anomaly"].known_group(key)
    pred = pipeline.predict(row)[0]
    return PredictResponse(predicted_yield_bu_acre=float(pred), known_county=bool(known))
