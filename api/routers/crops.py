"""GET /crops -- driven entirely by src/config.py CROPS. Adding a crop there
(plus its upstream data) requires zero changes here or in the frontend's
crop selector, which renders off this endpoint instead of hardcoded names.
"""
from fastapi import APIRouter

from config import CROPS

from ..models import CropMeta

router = APIRouter()


@router.get("/crops", response_model=list[CropMeta])
def list_crops():
    return [
        CropMeta(id=crop_id, display_name=meta["display_name"], nass_commodity=meta["nass_commodity"])
        for crop_id, meta in CROPS.items()
    ]
