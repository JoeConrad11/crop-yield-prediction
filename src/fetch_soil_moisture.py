"""Pull county-level soil moisture via Google Earth Engine, one row per
(year, county, period).

Uses ERA5-Land daily aggregate (volumetric_soil_water_layer_1, the 0-7cm
topsoil layer) rather than NASA SMAP -- SMAP's satellite record only starts
April 2015, which would leave 2010-2014 with no soil moisture data at all.
ERA5-Land is a reanalysis product (model + observations blended) with full
coverage back to 1950, so it stays consistent across our whole 2010-2023
study window at the cost of being modeled rather than directly measured.
"""
import os
import ee
import pandas as pd
from dotenv import load_dotenv

from config import STATE_FIPS, YEAR_START, YEAR_END, PERIODS

from gee_auth import ensure_initialized
ensure_initialized()

COUNTIES = ee.FeatureCollection("TIGER/2018/Counties")
ERA5_LAND = ee.ImageCollection("ECMWF/ERA5_LAND/DAILY_AGGR")


def fetch_period_soil_moisture(state_fips_list: list, year_start: int, year_end: int,
                                period_name: str, start_md: str, end_md: str) -> pd.DataFrame:
    counties = COUNTIES.filter(ee.Filter.inList("STATEFP", state_fips_list))
    rows = []
    for year in range(year_start, year_end + 1):
        start = f"{year}-{start_md}"
        end = f"{year}-{end_md}"
        soil_moisture = (
            ERA5_LAND.filterDate(start, end)
            .select("volumetric_soil_water_layer_1")
            .mean()
            .rename("soil_moisture_vol")
        )
        stats = soil_moisture.reduceRegions(
            collection=counties,
            reducer=ee.Reducer.mean(),
            scale=11000,  # native ERA5-Land resolution ~11km
        )
        features = stats.getInfo()["features"]
        for f in features:
            props = f["properties"]
            rows.append({
                "year": year,
                "period": period_name,
                "state_fips": props.get("STATEFP"),
                "county_fips": props.get("COUNTYFP"),
                "county_name": props.get("NAME"),
                "soil_moisture_vol": props.get("mean"),
            })
        print(f"  [{period_name}] fetched {year}: {len(features)} counties")
    return pd.DataFrame(rows)


if __name__ == "__main__":
    frames = []
    for period_name, (start_md, end_md) in PERIODS.items():
        print(f"Period: {period_name} ({start_md} to {end_md})")
        frames.append(fetch_period_soil_moisture(STATE_FIPS, YEAR_START, YEAR_END, period_name, start_md, end_md))
    df = pd.concat(frames, ignore_index=True)
    out_path = "data/raw/soil_moisture_periods.csv"
    df.to_csv(out_path, index=False)
    print(f"Saved {len(df)} rows to {out_path}")
