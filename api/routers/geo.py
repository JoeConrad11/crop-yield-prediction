"""GET /geo/counties -- serves the county boundary GeoJSON built by
scripts/build_county_geojson.py. Static file, not Supabase-backed --
boundaries don't change week to week the way predictions do, so there's no
need to round-trip this through the database.
"""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()

GEOJSON_PATH = Path(__file__).resolve().parents[1] / "data" / "counties.geojson"


@router.get("/geo/counties")
def counties():
    return FileResponse(GEOJSON_PATH, media_type="application/geo+json")
