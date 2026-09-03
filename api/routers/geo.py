"""GET /geo/counties, GET /geo/states -- serve the static boundary GeoJSONs
built by scripts/build_county_geojson.py and build_states_geojson.py. Not
Supabase-backed -- boundaries don't change week to week like predictions do.
`/geo/states` is a full-US backdrop (context so the 4 project states don't
render as shapes floating in empty space), not just this project's states.
"""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@router.get("/geo/counties")
def counties():
    return FileResponse(DATA_DIR / "counties.geojson", media_type="application/geo+json")


@router.get("/geo/states")
def states():
    return FileResponse(DATA_DIR / "states.geojson", media_type="application/geo+json")
