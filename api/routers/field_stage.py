"""POST /fields/stage -- where a field's crop is in its development, from
the farmer's planting date plus accumulated heat (see
src/field_insights.py and ARCHITECTURE.md's agronomy section).

Kept as its own endpoint rather than folded into /fields/predict on
purpose: the yield endpoint correctly refuses on fields too small for
today's imagery to resolve, and growth stage must stay available to exactly
those farmers. It comes from 4km temperature data, so field size is
irrelevant to its quality.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import CROPS
from field_insights import field_growth_stage, field_stage_benchmark

router = APIRouter()


class FieldStageRequest(BaseModel):
    boundary: dict
    crop: str
    planting_date: Optional[str] = None
    field_id: Optional[str] = None


@router.post("/fields/stage")
def field_stage_endpoint(req: FieldStageRequest):
    if req.crop not in CROPS:
        raise HTTPException(400, f"Unknown crop '{req.crop}'")

    result = field_growth_stage(req.boundary, req.crop, req.planting_date, date.today())
    if "error" in result:
        # Same convention as /fields/predict: a well-formed request with an
        # honest "can't answer this" outcome is a limitation, not a failure,
        # and carries a code so the UI can present it as such.
        raise HTTPException(422, {"code": result["error"], "message": result["message"]})
    return result


@router.post("/fields/benchmark")
def field_benchmark_endpoint(req: FieldStageRequest):
    """How this field's canopy compares to ITSELF in prior seasons, sampled
    at the same growth stage rather than the same calendar week.

    Slower than the other endpoints (it walks several years of daily
    temperature to locate each season's equivalent development date, then
    composites Sentinel-2 around each), but it is the one insight that
    stays reliable at ANY field size -- it never leaves Sentinel-2, so the
    cross-sensor calibration problem that blocks the yield path for small
    fields doesn't apply. See ARCHITECTURE.md, "What a small farm can
    actually be told."
    """
    if req.crop not in CROPS:
        raise HTTPException(400, f"Unknown crop '{req.crop}'")

    result = field_stage_benchmark(req.boundary, req.crop, req.planting_date, date.today())
    if "error" in result:
        raise HTTPException(422, {"code": result["error"], "message": result["message"]})
    return result
