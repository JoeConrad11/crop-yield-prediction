"""Pull county-level NDVI (MODIS), masked to a given crop's pixels via the
USDA Cropland Data Layer, using Google Earth Engine. Fetches one row per
(year, county, period), where period is a growing-season month (jun/jul/aug)
-- this gives the model a trajectory across the season instead of one flat
average."""
import os
import ee
import pandas as pd
from dotenv import load_dotenv

from config import YEAR_START, YEAR_END, CROPS, crop_state_fips, crop_periods

from gee_auth import ensure_initialized
ensure_initialized()

COUNTIES = ee.FeatureCollection("TIGER/2018/Counties")
CDL = ee.ImageCollection("USDA/NASS/CDL")
S2 = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")


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


def fetch_period_ndvi_for_field(geometry: ee.Geometry, year: int, period_name: str, start_md: str, end_md: str,
                                 cdl_code: int, cdl_year: int = None) -> dict:
    """Same crop-masked NDVI as fetch_period_ndvi, but reduced over a single
    farmer-drawn field polygon instead of every county in a FeatureCollection
    -- reduceRegion (one geometry) instead of reduceRegions (many). Honest
    caveat: MODIS is 250m/pixel, so a typical field is only a handful of
    pixels wide -- crop_pixel_count here will often be much smaller than any
    county's, and a single-digit count is a real precision limit, not a bug
    (see README "Known limitations" / ARCHITECTURE.md's Phase 1 constraint
    note -- Sentinel-2's 10m would fix this, MODIS can't)."""
    start = f"{year}-{start_md}"
    end = f"{year}-{end_md}"
    ndvi = (
        ee.ImageCollection("MODIS/061/MOD13Q1")
        .filterDate(start, end)
        .select("NDVI")
        .mean()
        .multiply(0.0001)
    )
    crop_ndvi = ndvi.updateMask(crop_mask_for_year(cdl_year or year, cdl_code))
    # reduceRegion (this function) band-prefixes combined-reducer output keys
    # even for a single band -- "NDVI_mean"/"NDVI_count" -- UNLIKE
    # reduceRegions (the county path above), which doesn't prefix a single
    # band's combined-reducer output ("mean"/"count"). Confirmed by hand:
    # same image/reducer/geometry, only the API differs, and the key names
    # differ with it. Don't copy this function's key names into a
    # reduceRegions call, or vice versa.
    stats = crop_ndvi.reduceRegion(
        reducer=ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True),
        geometry=geometry,
        scale=250,
        maxPixels=1e9,
    ).getInfo()
    return {
        "year": year,
        "period": period_name,
        "ndvi_mean": stats.get("NDVI_mean"),
        "crop_pixel_count": stats.get("NDVI_count"),
        "pixel_scale_m": 250,
    }


# Cloud Score+ -- a per-pixel usability score (0 = occluded, 1 = clear)
# published by Google for the harmonized S2 archive, and the current
# best-practice masker for Sentinel-2 in Earth Engine.
CS_PLUS = ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED")

# Keep pixels at least this clear. 0.6 is Google's own suggested starting
# threshold; lower keeps more (hazier) pixels, higher is stricter but can
# empty out a composite in a persistently cloudy month.
CS_PLUS_THRESHOLD = 0.6


def _mask_s2_clouds_qa60(image: ee.Image) -> ee.Image:
    """QA60 bitmask cloud/cirrus mask (bits 10/11) -- the old lightweight
    approach, KEPT ONLY as the documented baseline for the Phase 4a
    validation comparison (see ARCHITECTURE.md). Do not use it for new
    work: QA60 misses haze and thin cirrus, and Sentinel-2's processing
    baseline change in early 2022 left the band largely empty on newer
    scenes, so it silently degrades exactly where it looks like it's
    working. Measured cost of that: monthly medians built on this mask
    correlated with county corn yield at r=0.25 pooled, versus MODIS's
    r=0.43 -- the extra spread was contamination, not signal."""
    qa = image.select("QA60")
    cloud_bit = 1 << 10
    cirrus_bit = 1 << 11
    mask = qa.bitwiseAnd(cloud_bit).eq(0).And(qa.bitwiseAnd(cirrus_bit).eq(0))
    return image.updateMask(mask).divide(10000)  # reflectance scale factor


def _s2_ndvi_composite(start: str, end: str, region: ee.Geometry,
                        cs_threshold: float = CS_PLUS_THRESHOLD) -> ee.Image:
    """Cloud-masked median composite NDVI over the date range, restricted to
    `region` via filterBounds -- unlike MODIS/061/MOD13Q1 (already a
    pre-cleaned 16-day composite product), raw Sentinel-2 scenes need this
    compositing step done ourselves.

    Masking uses Cloud Score+ (linkCollection joins its `cs` band onto each
    scene by system:index), not QA60 -- see _mask_s2_clouds_qa60's docstring
    for the measured reason. filterBounds matters here beyond tidiness:
    without it the collection is every Sentinel-2 granule on Earth for the
    date range before lazy evaluation gets a chance to narrow it down."""
    collection = (
        S2.filterDate(start, end)
        .filterBounds(region)
        .linkCollection(CS_PLUS, ["cs"])
        .map(lambda img: img.updateMask(img.select("cs").gte(cs_threshold)).divide(10000))
    )
    composite = collection.median()
    return composite.normalizedDifference(["B8", "B4"]).rename("NDVI")


def fetch_period_ndvi_s2_for_field(geometry: ee.Geometry, year: int, period_name: str, start_md: str, end_md: str,
                                    cdl_code: int, cdl_year: int = None) -> dict:
    """Phase 4a (see ../ARCHITECTURE.md): same crop-masked NDVI as
    fetch_period_ndvi_for_field, but from Sentinel-2 (10m/pixel) instead of
    MODIS (250m/pixel) -- ~625x the pixel density, which is what actually
    lets a field under ~40-60 acres return a usable NDVI signal at all
    (fetch_period_ndvi_for_field's crop_pixel_count often comes back 0 at
    that size; see ARCHITECTURE.md's Phase 4 writeup for why this was
    added). NOT wired into the live field-prediction path yet -- see
    validate_sentinel2_ndvi.py, which checks whether Sentinel-2's NDVI
    values need a correction toward MODIS's scale (different sensor,
    different band responses/compositing) before a MODIS-calibrated model
    can trust them."""
    start = f"{year}-{start_md}"
    end = f"{year}-{end_md}"
    ndvi = _s2_ndvi_composite(start, end, geometry)
    crop_ndvi = ndvi.updateMask(crop_mask_for_year(cdl_year or year, cdl_code))
    # Same reduceRegion band-prefixing behavior as fetch_period_ndvi_for_field
    # (NDVI_mean/NDVI_count, not mean/count) -- see that function's comment.
    stats = crop_ndvi.reduceRegion(
        reducer=ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True),
        geometry=geometry,
        scale=10,
        maxPixels=1e9,
    ).getInfo()
    return {
        "year": year,
        "period": period_name,
        "ndvi_mean": stats.get("NDVI_mean"),
        "crop_pixel_count": stats.get("NDVI_count"),
        "pixel_scale_m": 10,
    }


def fetch_period_ndvi_s2(state_fips_list: list, year_start: int, year_end: int,
                          period_name: str, start_md: str, end_md: str, cdl_code: int,
                          cdl_year: int = None, scale: int = 100) -> pd.DataFrame:
    """County-level Sentinel-2 NDVI, same shape as fetch_period_ndvi -- built
    ONLY for validate_sentinel2_ndvi.py to compare against the already-
    fetched MODIS county data (data/raw/gee_ndvi_<crop>_periods.csv), NOT
    part of the live pipeline (that's fetch_period_ndvi_s2_for_field above).
    scale=100 (not the field-level function's 10m): a whole county's worth
    of pixels at native 10m is far more compute than this comparison needs
    -- we only need a representative per-county MEAN to correlate against
    MODIS's own 250m-native county mean, and Sentinel-2 at 100m is still
    2.5x finer than MODIS."""
    counties = COUNTIES.filter(ee.Filter.inList("STATEFP", state_fips_list))
    rows = []
    for year in range(year_start, year_end + 1):
        start = f"{year}-{start_md}"
        end = f"{year}-{end_md}"
        ndvi = _s2_ndvi_composite(start, end, counties)
        crop_ndvi = ndvi.updateMask(crop_mask_for_year(cdl_year or year, cdl_code))
        stats = crop_ndvi.reduceRegions(
            collection=counties,
            reducer=ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True),
            scale=scale,
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
                "ndvi_mean_s2": props.get("mean"),
                "crop_pixel_count_s2": props.get("count"),
            })
        print(f"  [S2 {period_name}] fetched {year}: {len(features)} counties")
    return pd.DataFrame(rows)


if __name__ == "__main__":
    import sys
    crops = sys.argv[1:] or list(CROPS.keys())
    for crop in crops:
        cdl_code = CROPS[crop]["cdl_code"]
        frames = []
        for period_name, (start_md, end_md) in crop_periods(crop).items():
            print(f"Crop: {crop}, Period: {period_name} ({start_md} to {end_md})")
            frames.append(fetch_period_ndvi(crop_state_fips(crop), YEAR_START, YEAR_END, period_name, start_md, end_md, cdl_code))
        df = pd.concat(frames, ignore_index=True)
        out_path = f"data/raw/gee_ndvi_{crop}_periods.csv"
        df.to_csv(out_path, index=False)
        print(f"Saved {len(df)} rows to {out_path}\n")
