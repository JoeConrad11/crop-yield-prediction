"""GET /predictions/history -- year-by-year actual yield for one county, from
the same model_table_<crop>_pre_harvest.csv used to train the production
models (not Supabase -- this is static historical data that doesn't change
week to week, unlike live_predictions). Crop-generic: the file naming
pattern already keys off src/config.py CROPS, so a new crop's history is
available the moment its model_table CSV exists, no code change here.
"""
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"


@router.get("/predictions/history")
def yield_history(
    crop: str = Query(...),
    state: str = Query(..., description="2-digit state FIPS"),
    county: str = Query(..., description="3-digit county FIPS"),
):
    path = DATA_DIR / f"model_table_{crop}_pre_harvest.csv"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"No history table for crop '{crop}'")

    df = pd.read_csv(path, usecols=["year", "state_fips", "county_fips", "yield_bu_acre"])
    df["state_fips"] = df["state_fips"].astype(str).str.zfill(2)
    df["county_fips"] = df["county_fips"].astype(str).str.zfill(3)

    rows = df[(df["state_fips"] == state) & (df["county_fips"] == county)].sort_values("year")
    return [
        {"year": int(r.year), "yield_bu_acre": float(r.yield_bu_acre)}
        for r in rows.itertuples()
    ]


BACKTEST_PATH = DATA_DIR / "backtest_predictions.csv"


@router.get("/predictions/backtest")
def backtest_predictions(
    crop: str = Query(...),
    state: str = Query(..., description="2-digit state FIPS"),
    county: str = Query(..., description="3-digit county FIPS"),
    checkpoint: str = Query("pre_harvest"),
):
    """True held-out (leave-one-year-out) predictions for every year in
    config.YEAR_START-YEAR_END -- NOT the production model's in-sample fit.
    See src/backtest_recent_years.py for what "held-out" means for years
    other than the 2 most recent (still real cross-validation, just not a
    literal replay of what was knowable live at the time)."""
    if not BACKTEST_PATH.exists():
        raise HTTPException(status_code=404, detail="Backtest predictions not generated yet")

    df = pd.read_csv(BACKTEST_PATH)
    df["state_fips"] = df["state_fips"].astype(str).str.zfill(2)
    df["county_fips"] = df["county_fips"].astype(str).str.zfill(3)

    rows = df[
        (df["crop"] == crop)
        & (df["checkpoint"] == checkpoint)
        & (df["state_fips"] == state)
        & (df["county_fips"] == county)
    ].sort_values("year")
    return [
        {
            "year": int(r.year),
            "actual_yield_bu_acre": float(r.actual_yield_bu_acre),
            "predicted_yield_bu_acre": float(r.predicted_yield_bu_acre),
        }
        for r in rows.itertuples()
    ]
