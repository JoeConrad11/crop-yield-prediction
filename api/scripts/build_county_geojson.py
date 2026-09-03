"""One-off script: download US Census county boundaries and write a GeoJSON
filtered to this project's states, keyed by the same state_fips/county_fips
convention used throughout src/. Not part of the Modal cron (src/run_pipeline.py)
-- county boundaries don't change week to week the way predictions do.

Run manually from the repo root: .venv/bin/python3 api/scripts/build_county_geojson.py
Requires geopandas (see api/requirements.txt) -- not a dependency of the API
service itself, only of this script.
"""
import io
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from config import STATE_FIPS  # noqa: E402

SHAPEFILE_URL = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_500k.zip"
OUT_PATH = Path(__file__).resolve().parents[1] / "data" / "counties.geojson"


def main():
    print(f"Downloading {SHAPEFILE_URL} ...")
    resp = requests.get(SHAPEFILE_URL, timeout=120)
    resp.raise_for_status()

    tmp_dir = OUT_PATH.parent / "_tmp_shapefile"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            zf.extractall(tmp_dir)
        shp_path = next(tmp_dir.glob("*.shp"))
        counties = gpd.read_file(shp_path)

        counties = counties[counties["STATEFP"].isin(STATE_FIPS)].copy()
        counties = counties.rename(
            columns={"STATEFP": "state_fips", "COUNTYFP": "county_fips", "NAME": "county_name"}
        )
        counties = counties[["state_fips", "county_fips", "county_name", "geometry"]]

        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        if OUT_PATH.exists():
            OUT_PATH.unlink()
        counties.to_file(OUT_PATH, driver="GeoJSON")
        print(f"Saved {len(counties)} county polygons to {OUT_PATH}")
    finally:
        for f in tmp_dir.glob("*"):
            f.unlink()
        tmp_dir.rmdir()


if __name__ == "__main__":
    main()
