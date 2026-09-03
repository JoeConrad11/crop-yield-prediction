"""One-off script: download US state boundaries (all 50 + DC) and write a
GeoJSON used purely as a gray context backdrop behind the county choropleth
-- without it, the 4 project states render as disconnected shapes floating
in empty space with no sense of where they sit in the country.

Run manually from the repo root: .venv/bin/python3 api/scripts/build_states_geojson.py
Requires geopandas (see api/requirements.txt), same as build_county_geojson.py.
"""
import io
import zipfile
from pathlib import Path

import geopandas as gpd
import requests

SHAPEFILE_URL = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_state_500k.zip"
OUT_PATH = Path(__file__).resolve().parents[1] / "data" / "states.geojson"


def main():
    print(f"Downloading {SHAPEFILE_URL} ...")
    resp = requests.get(SHAPEFILE_URL, timeout=120)
    resp.raise_for_status()

    tmp_dir = OUT_PATH.parent / "_tmp_states_shapefile"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            zf.extractall(tmp_dir)
        shp_path = next(tmp_dir.glob("*.shp"))
        states = gpd.read_file(shp_path)

        # Drop territories/far-flung areas geoAlbersUsa doesn't place
        # meaningfully next to the mainland cluster this project cares about.
        states = states[~states["STUSPS"].isin(["PR", "VI", "GU", "AS", "MP"])].copy()
        states = states.rename(columns={"STATEFP": "state_fips", "NAME": "state_name"})
        states = states[["state_fips", "state_name", "geometry"]]

        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        if OUT_PATH.exists():
            OUT_PATH.unlink()
        states.to_file(OUT_PATH, driver="GeoJSON")
        print(f"Saved {len(states)} state polygons to {OUT_PATH}")
    finally:
        for f in tmp_dir.glob("*"):
            f.unlink()
        tmp_dir.rmdir()


if __name__ == "__main__":
    main()
