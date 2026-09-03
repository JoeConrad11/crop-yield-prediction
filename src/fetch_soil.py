"""Pull static county-level soil properties from OpenLandMap (via Google
Earth Engine) -- organic carbon, pH, clay %, sand %, and available water
capacity. Unlike NDVI/weather, soil doesn't meaningfully change year to
year at this timescale, so this is one fetch per county, not per year."""
import os
import ee
import pandas as pd
from dotenv import load_dotenv

from config import STATE_FIPS

from gee_auth import ensure_initialized
ensure_initialized()

COUNTIES = ee.FeatureCollection("TIGER/2018/Counties")

# band 'b0' = 0cm depth for all of these OpenLandMap layers
SOIL_LAYERS = {
    "soil_organic_carbon": "OpenLandMap/SOL/SOL_ORGANIC-CARBON_USDA-6A1C_M/v02",
    "soil_ph": "OpenLandMap/SOL/SOL_PH-H2O_USDA-4C1A2A_M/v02",
    "soil_clay_pct": "OpenLandMap/SOL/SOL_CLAY-WFRACTION_USDA-3A1A1A_M/v02",
    "soil_sand_pct": "OpenLandMap/SOL/SOL_SAND-WFRACTION_USDA-3A1A1A_M/v02",
    "soil_water_content_33kpa": "OpenLandMap/SOL/SOL_WATERCONTENT-33KPA_USDA-4B1C_M/v01",
}


def fetch_county_soil(state_fips_list: list) -> pd.DataFrame:
    counties = COUNTIES.filter(ee.Filter.inList("STATEFP", state_fips_list))

    combined = None
    for feature_name, asset_id in SOIL_LAYERS.items():
        band = ee.Image(asset_id).select(0).rename(feature_name)
        combined = band if combined is None else combined.addBands(band)

    stats = combined.reduceRegions(
        collection=counties,
        reducer=ee.Reducer.mean(),
        scale=250,
    )
    features = stats.getInfo()["features"]
    rows = []
    for f in features:
        props = f["properties"]
        row = {
            "state_fips": props.get("STATEFP"),
            "county_fips": props.get("COUNTYFP"),
            "county_name": props.get("NAME"),
        }
        row.update({name: props.get(name) for name in SOIL_LAYERS})
        rows.append(row)
    print(f"  fetched {len(features)} counties")
    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = fetch_county_soil(STATE_FIPS)
    out_path = "data/raw/soil_properties.csv"
    df.to_csv(out_path, index=False)
    print(f"Saved {len(df)} rows to {out_path}")
    print(df.head())
