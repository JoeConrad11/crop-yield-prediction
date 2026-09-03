"""Pull county-level weather (PRISM daily) via Google Earth Engine, one row
per (year, county, period), where period is a growing-season month.

Uses OREGONSTATE/PRISM/ANd (4km daily CONUS grid: precip, tmin, tmax, tmean)
instead of downloading raw PRISM rasters, so it reuses the same GEE auth/county
pipeline as fetch_gee.py.
"""
import os
import ee
import pandas as pd
from dotenv import load_dotenv

from config import STATE_FIPS, YEAR_START, YEAR_END, PERIODS

from gee_auth import ensure_initialized
ensure_initialized()

COUNTIES = ee.FeatureCollection("TIGER/2018/Counties")
PRISM = ee.ImageCollection("OREGONSTATE/PRISM/ANd")


def fetch_period_weather(state_fips_list: list, year_start: int, year_end: int,
                          period_name: str, start_md: str, end_md: str) -> pd.DataFrame:
    """Cumulative precip + mean tmin/tmax/tmean over one month, per county per year."""
    counties = COUNTIES.filter(ee.Filter.inList("STATEFP", state_fips_list))
    rows = []
    for year in range(year_start, year_end + 1):
        start = f"{year}-{start_md}"
        end = f"{year}-{end_md}"
        month = PRISM.filterDate(start, end)

        precip_sum = month.select("ppt").sum()
        tmean_avg = month.select("tmean").mean()
        tmax_avg = month.select("tmax").mean()
        tmin_avg = month.select("tmin").mean()

        combined = precip_sum.rename("precip_sum_mm") \
            .addBands(tmean_avg.rename("tmean_c")) \
            .addBands(tmax_avg.rename("tmax_c")) \
            .addBands(tmin_avg.rename("tmin_c"))

        stats = combined.reduceRegions(
            collection=counties,
            reducer=ee.Reducer.mean(),
            scale=4000,
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
                "precip_sum_mm": props.get("precip_sum_mm"),
                "tmean_c": props.get("tmean_c"),
                "tmax_c": props.get("tmax_c"),
                "tmin_c": props.get("tmin_c"),
            })
        print(f"  [{period_name}] fetched {year}: {len(features)} counties")
    return pd.DataFrame(rows)


if __name__ == "__main__":
    frames = []
    for period_name, (start_md, end_md) in PERIODS.items():
        print(f"Period: {period_name} ({start_md} to {end_md})")
        frames.append(fetch_period_weather(STATE_FIPS, YEAR_START, YEAR_END, period_name, start_md, end_md))
    df = pd.concat(frames, ignore_index=True)
    out_path = "data/raw/prism_weather_periods.csv"
    df.to_csv(out_path, index=False)
    print(f"Saved {len(df)} rows to {out_path}")
