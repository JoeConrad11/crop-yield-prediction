"""GET /predictions, GET /predictions/latest -- reads live_predictions,
which is already long/tidy (one row per crop/county), so these endpoints
work unchanged as more crops are added to src/config.py CROPS.
"""
from typing import Optional

from fastapi import APIRouter, Query

from ..db import get_client
from ..models import PredictionOut

router = APIRouter()


def _parse_crops(crop: Optional[str]) -> Optional[list[str]]:
    return crop.split(",") if crop else None


def _filtered(query, crop: Optional[str], state: Optional[str], county: Optional[str]):
    crops = _parse_crops(crop)
    if crops:
        query = query.in_("crop", crops)
    if state:
        query = query.eq("state_fips", state)
    if county:
        query = query.eq("county_fips", county)
    return query


@router.get("/predictions/latest", response_model=list[PredictionOut])
def latest_predictions(
    crop: Optional[str] = Query(None, description="Comma-separated crop ids, omit for all"),
    state: Optional[str] = Query(None, description="2-digit state FIPS"),
    county: Optional[str] = Query(None, description="3-digit county FIPS"),
):
    client = get_client()
    latest = (
        client.table("live_predictions")
        .select("as_of_date")
        .order("as_of_date", desc=True)
        .limit(1)
        .execute()
    )
    if not latest.data:
        return []
    as_of = latest.data[0]["as_of_date"]

    query = client.table("live_predictions").select("*").eq("as_of_date", as_of)
    return _filtered(query, crop, state, county).execute().data


@router.get("/predictions", response_model=list[PredictionOut])
def predictions(
    as_of: str = Query(..., description="YYYY-MM-DD"),
    crop: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    county: Optional[str] = Query(None),
):
    client = get_client()
    query = client.table("live_predictions").select("*").eq("as_of_date", as_of)
    return _filtered(query, crop, state, county).execute().data
