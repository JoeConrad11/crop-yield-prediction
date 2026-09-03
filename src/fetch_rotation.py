"""Pull a county-level crop-rotation signal: for each (year, county, crop),
what fraction of this year's crop-masked pixels were the SAME crop in the
prior year's Cropland Data Layer.

This is built entirely from CDL (which we already pull for the crop mask in
fetch_gee.py), not an assumed literature constant -- it lets the yield model
learn the actual empirical yield effect of continuous cropping vs rotation
from real county-year data, the same way every other feature in this
pipeline was built.

Static per (year, county, crop) -- one fetch per crop, not per period, since
rotation doesn't change within a growing season.
"""
import pandas as pd

from config import STATE_FIPS, YEAR_START, YEAR_END, CROPS
from fetch_gee import COUNTIES, CDL, crop_mask_for_year
import ee


def fetch_rotation_signal(state_fips_list: list, year_start: int, year_end: int, cdl_code: int) -> pd.DataFrame:
    """pct_continuous: of this year's crop pixels, the fraction that were the
    same crop last year too (1.0 = fully continuous, 0.0 = fully rotated in)."""
    counties = COUNTIES.filter(ee.Filter.inList("STATEFP", state_fips_list))
    rows = []
    for year in range(year_start, year_end + 1):
        this_year_mask = crop_mask_for_year(year, cdl_code)
        prev_year_image = CDL.filter(ee.Filter.calendarRange(year - 1, year - 1, "year")).first()
        was_same_crop_last_year = prev_year_image.select("cropland").eq(cdl_code)
        continuous_indicator = was_same_crop_last_year.updateMask(this_year_mask).rename("continuous")

        stats = continuous_indicator.reduceRegions(
            collection=counties,
            reducer=ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True),
            scale=250,
        )
        features = stats.getInfo()["features"]
        for f in features:
            props = f["properties"]
            rows.append({
                "year": year,
                "state_fips": props.get("STATEFP"),
                "county_fips": props.get("COUNTYFP"),
                "county_name": props.get("NAME"),
                "pct_continuous": props.get("mean"),
                "rotation_pixel_count": props.get("count"),
            })
        print(f"  fetched {year}: {len(features)} counties")
    return pd.DataFrame(rows)


if __name__ == "__main__":
    import sys
    crops = sys.argv[1:] or list(CROPS.keys())
    for crop in crops:
        print(f"Crop: {crop}")
        df = fetch_rotation_signal(STATE_FIPS, YEAR_START, YEAR_END, CROPS[crop]["cdl_code"])
        out_path = f"data/raw/rotation_{crop}.csv"
        df.to_csv(out_path, index=False)
        print(f"Saved {len(df)} rows to {out_path}\n")
