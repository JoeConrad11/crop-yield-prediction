"""POST /fields/predict -- Phase 3 of the farmer-app roadmap (see
../../ARCHITECTURE.md). Unlike every other router here (which reads
pre-computed rows Supabase already has, written by the Modal cron in
src/run_pipeline.py), this one calls Earth Engine and the trained model
directly inside the request -- a farmer clicks "predict my field" and waits
several seconds for a handful of live GEE reduceRegion calls, not a
pre-batched county sweep. No Supabase read/write here: the field boundary
itself lives in Supabase, but fetching it is the frontend's job, keeping
this endpoint stateless with respect to farmer accounts.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import CROPS
from predict_field import predict_field

from ..models import FieldPredictionOut

router = APIRouter()


class FieldPredictRequest(BaseModel):
    # GeoJSON Polygon, the exact shape frontend/lib/geo.ts's
    # polygonToGeoJSON() produces and fields.boundary stores in Supabase.
    boundary: dict
    crop: str
    field_id: Optional[str] = None


@router.post("/fields/predict", response_model=FieldPredictionOut)
def predict_field_endpoint(req: FieldPredictRequest):
    if req.crop not in CROPS:
        raise HTTPException(400, f"Unknown crop '{req.crop}'")

    result = predict_field(req.boundary, req.crop, date.today(), field_id=req.field_id)
    if "error" in result:
        # 422 (not 500): a well-formed request that came back with an honest
        # "can't predict this" answer, not a server failure. The `code` is
        # passed through structurally rather than only as prose because
        # these are LIMITATIONS, not errors -- a small field hitting
        # `unreliable_coverage` is the single most likely outcome for the
        # farmers this product is aimed at (MODIS is 15.4 acres/pixel), and
        # the UI needs to present that as a known constraint of the current
        # imagery rather than as something the farmer did wrong.
        raise HTTPException(422, {"code": result["error"], "message": result["message"]})
    return result
