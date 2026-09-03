"""Pydantic response models -- mirror src/supabase_schema.sql, not a
separate source of truth. Crop identity is always a free-form `crop: str`
(whatever's in src/config.py CROPS), never an enum, so a new crop needs no
model change here.
"""
from typing import Optional

from pydantic import BaseModel


class CropMeta(BaseModel):
    id: str
    display_name: str
    nass_commodity: str


class PredictionOut(BaseModel):
    crop: str
    year: int
    state_fips: str
    county_fips: str
    county_name: str
    checkpoint: str
    predicted_yield_bu_acre: float
    predicted_yield_low: Optional[float] = None
    predicted_yield_high: Optional[float] = None
    confidence_mae: Optional[float] = None
    coverage_tier: Optional[str] = None
    crop_pixel_coverage: Optional[float] = None
    historical_avg_yield: Optional[float] = None
    delta_vs_historical: Optional[float] = None
    pct_vs_historical: Optional[float] = None


class CropProfitability(BaseModel):
    yield_bu_acre: Optional[float] = None
    price_per_bu: Optional[float] = None
    cost_per_acre: Optional[float] = None
    revenue_per_acre: Optional[float] = None
    profit_per_acre: Optional[float] = None


class CountyComparisonOut(BaseModel):
    state_fips: str
    county_fips: str
    county_name: str
    state_alpha: str
    crops: dict[str, CropProfitability]
    best_crop: Optional[str] = None
    margin_dollars: Optional[float] = None
