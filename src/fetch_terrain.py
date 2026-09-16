"""Pull static county-level terrain (elevation, slope) from SRTM via Google
Earth Engine. Static like soil -- one fetch per county, not per year."""
import os
import ee
import pandas as pd
from dotenv import load_dotenv

from config import STATE_FIPS

from gee_auth import ensure_initialized
ensure_initialized()

COUNTIES = ee.FeatureCollection("TIGER/2018/Counties")


def fetch_county_terrain(state_fips_list: list) -> pd.DataFrame:
    counties = COUNTIES.filter(ee.Filter.inList("STATEFP", state_fips_list))

    dem = ee.Image("USGS/SRTMGL1_003").rename("elevation_m")
    slope = ee.Terrain.slope(dem).rename("slope_deg")
    combined = dem.addBands(slope)

    stats = combined.reduceRegions(
        collection=counties,
        reducer=ee.Reducer.mean(),
        scale=30,
    )
    features = stats.getInfo()["features"]
    rows = []
    for f in features:
        props = f["properties"]
        rows.append({
            "state_fips": props.get("STATEFP"),
            "county_fips": props.get("COUNTYFP"),
            "county_name": props.get("NAME"),
            "elevation_m": props.get("elevation_m"),
            "slope_deg": props.get("slope_deg"),
        })
    print(f"  fetched {len(features)} counties")
    return pd.DataFrame(rows)


def fetch_field_terrain(geometry: ee.Geometry) -> dict:
    """Same SRTM elevation/slope as fetch_county_terrain, reduced over a
    single field polygon (reduceRegion) instead of every county
    (reduceRegions). Static -- call once per field and cache the result,
    see fetch_field_features.py."""
    dem = ee.Image("USGS/SRTMGL1_003").rename("elevation_m")
    slope = ee.Terrain.slope(dem).rename("slope_deg")
    combined = dem.addBands(slope)

    stats = combined.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=geometry,
        scale=30,
        maxPixels=1e9,
    ).getInfo()
    return {"elevation_m": stats.get("elevation_m"), "slope_deg": stats.get("slope_deg")}


if __name__ == "__main__":
    df = fetch_county_terrain(STATE_FIPS)
    out_path = "data/raw/terrain_properties.csv"
    df.to_csv(out_path, index=False)
    print(f"Saved {len(df)} rows to {out_path}")
    print(df.head())
