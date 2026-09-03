"""Pull county-level NDVI (MODIS), masked to a given crop's pixels via the
USDA Cropland Data Layer, using Google Earth Engine. Fetches one row per
(year, county, period), where period is a growing-season month (jun/jul/aug)
-- this gives the model a trajectory across the season instead of one flat
average."""
import os
import ee
import pandas as pd
from dotenv import load_dotenv

from config import YEAR_START, YEAR_END, PERIODS, CROPS, crop_state_fips

from gee_auth import ensure_initialized
ensure_initialized()

COUNTIES = ee.FeatureCollection("TIGER/2018/Counties")
CDL = ee.ImageCollection("USDA/NASS/CDL")


def crop_mask_for_year(year: int, cdl_code: int) -> ee.Image:
    """Binary mask (1 = this crop, masked out elsewhere) from that year's CDL."""
    cdl_image = CDL.filter(ee.Filter.calendarRange(year, year, "year")).first()
    return cdl_image.select("cropland").eq(cdl_code).selfMask()


def fetch_period_ndvi(state_fips_list: list, year_start: int, year_end: int,
                       period_name: str, start_md: str, end_md: str, cdl_code: int,
                       cdl_year: int = None) -> pd.DataFrame:
    """Mean NDVI over this crop's pixels only, per county per year, for one month.

    cdl_year overrides which year's Cropland Data Layer is used for the crop
    mask -- needed for live/current-season predictions, since CDL for a given
    year isn't published until after that year's harvest. Pass the most
    recent available CDL year as a proxy in that case."""
    counties = COUNTIES.filter(ee.Filter.inList("STATEFP", state_fips_list))
    rows = []
    for year in range(year_start, year_end + 1):
        start = f"{year}-{start_md}"
        end = f"{year}-{end_md}"
        ndvi = (
            ee.ImageCollection("MODIS/061/MOD13Q1")
            .filterDate(start, end)
            .select("NDVI")
            .mean()
            .multiply(0.0001)  # MODIS NDVI scale factor
        )
        crop_ndvi = ndvi.updateMask(crop_mask_for_year(cdl_year or year, cdl_code))
        stats = crop_ndvi.reduceRegions(
            collection=counties,
            reducer=ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True),
            scale=250,
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
                "ndvi_mean": props.get("mean"),
                "crop_pixel_count": props.get("count"),
            })
        print(f"  [{period_name}] fetched {year}: {len(features)} counties")
    return pd.DataFrame(rows)


if __name__ == "__main__":
    import sys
    crops = sys.argv[1:] or list(CROPS.keys())
    for crop in crops:
        cdl_code = CROPS[crop]["cdl_code"]
        frames = []
        for period_name, (start_md, end_md) in PERIODS.items():
            print(f"Crop: {crop}, Period: {period_name} ({start_md} to {end_md})")
            frames.append(fetch_period_ndvi(crop_state_fips(crop), YEAR_START, YEAR_END, period_name, start_md, end_md, cdl_code))
        df = pd.concat(frames, ignore_index=True)
        out_path = f"data/raw/gee_ndvi_{crop}_periods.csv"
        df.to_csv(out_path, index=False)
        print(f"Saved {len(df)} rows to {out_path}\n")
