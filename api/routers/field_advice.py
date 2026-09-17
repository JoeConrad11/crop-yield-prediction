"""POST /fields/advice -- Layer 3 of the farmer-app agronomy roadmap (see
src/field_advice.py and ARCHITECTURE.md). Pairs a field's prediction with
why it came out that way: the model's own SHAP explanation, plus (only when
the field's own stage/stress state actually warrants one) a cited land-grant
extension finding.

Kept as its own endpoint, same reasoning as field_stage.py: the SHAP half
needs a successful prediction, but the sourced-note half is keyed off growth
stage, which works at any field size -- so a small field the yield endpoint
correctly refuses can still get a sourced note back from this one.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import CROPS
from field_advice import field_advice

router = APIRouter()


class FieldAdviceRequest(BaseModel):
    boundary: dict
    crop: str
    planting_date: Optional[str] = None
    field_id: Optional[str] = None


@router.post("/fields/advice")
def field_advice_endpoint(req: FieldAdviceRequest):
    if req.crop not in CROPS:
        raise HTTPException(400, f"Unknown crop '{req.crop}'")

    return field_advice(req.boundary, req.crop, req.planting_date, date.today(), field_id=req.field_id)
