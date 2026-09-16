"""Phase 2 of the farmer-app roadmap (see ../ARCHITECTURE.md): pull the same
NDVI/weather/soil-moisture/soil/terrain/rotation features predict_live.py
builds per COUNTY, but for a single farmer-drawn field polygon instead --
using each fetch_*.py module's new `_for_field` function (reduceRegion over
one ee.Geometry) rather than the county path (reduceRegions over a
FeatureCollection).

Column names deliberately match predict_live.py's per-county feature row
exactly (ndvi_<period>, precip_sum_<period>, tmean_<period>, ...) -- that's
what lets Phase 3 apply the SAME county-calibrated model to this row without
a separate feature-mapping step. What Phase 3 still has to add: a
`state_<ALPHA>` one-hot column (which state dummy to set isn't derivable
from a field polygon alone without a spatial join against TIGER/2018/States,
not done here), and the actual model.predict() call.

IMPORTANT HONEST CAVEAT (see ARCHITECTURE.md's "core constraint"): this is
field-level INPUT through a county-calibrated MODEL, not a field-level-
trained model -- there is no field-level yield ground truth to train one.
Frame anything built on this as "vs. your county's trend," not an exact
bushels/acre guarantee.

Also honest about resolution: MODIS NDVI is 250m/pixel and CDL is 30m/pixel.
A typical field (tens of acres) may only cover a handful of MODIS pixels --
`crop_pixel_coverage` on the output row will often be far lower than any
county's, and that's a real precision limit (Sentinel-2's 10m would help,
MODIS can't), not a bug to hide.
"""
import json
import math
from datetime import date
from pathlib import Path

import ee

from config import CROPS, crop_periods, crop_checkpoints, all_periods
from fetch_gee import fetch_period_ndvi_for_field, COUNTIES, CDL
from fetch_prism import fetch_period_weather_for_field, fetch_period_stress_for_field
from fetch_soil_moisture import fetch_period_soil_moisture_for_field
from fetch_soil import fetch_field_soil
from fetch_terrain import fetch_field_terrain
from fetch_rotation import fetch_field_rotation
from predict_live import completed_periods, pick_checkpoint, latest_available_cdl_year
from build_dataset import STRESS_METRICS, NEEDS_STRESS

from gee_auth import ensure_initialized
ensure_initialized()

STATIC_CACHE_DIR = Path("data/processed/field_static_cache")

M2_PER_ACRE = 4046.8564224

# Coverage thresholds in ACRES OF CROP ACTUALLY OBSERVED, deliberately not
# in pixels. predict_live.coverage_tier() tiers on raw pixel count against
# MIN_CROP_PIXELS (=500), which is only meaningful for MODIS at county
# scale: the same field measured by MODIS (250m, 15.4 acres/pixel) and
# Sentinel-2 (10m, 0.025 acres/pixel) differs by ~625x in pixel count while
# being the exact same piece of ground. Any pixel-count threshold is
# therefore a statement about the sensor, not about the field. Area is the
# thing that actually governs whether an NDVI mean is trustworthy, and it
# stays fixed no matter which sensor reports it.
COVERAGE_HIGH_ACRES = 10.0
COVERAGE_MEDIUM_ACRES = 2.5

# How much of the field a single pixel may cover. Two thresholds, because
# the evidence supports a spectrum rather than a cliff:
#
#   > REFUSE_ABOVE  the reading is demonstrably about other land. Measured:
#                   on an 18.8-acre field (one MODIS pixel = 82% of it)
#                   MODIS reported 3 confident "corn" pixels at NDVI
#                   0.82-0.89 on ground that was 0.9% corn.
#   > DEGRADE_ABOVE the reading is field-ish but coarse, so it's allowed
#                   through capped at "low" confidence rather than refused.
#
# The 33% refusal line is set where a single pixel covers a third or more
# of the field; the 10% degrade line is where pixel count gets thin (~10
# pixels). Only the far end of this is measured -- the middle band is a
# judgement call, deliberately erring toward giving a labelled answer
# instead of nothing.
#
# Why not simply refuse everything coarse: a 250m pixel over-reports area
# by ~1.2-1.55x at EVERY field size (measured: 1.23x on 113 acres, 1.42x
# on 2731), so over-reach alone can't separate a usable field from an
# unusable one -- but pixel-to-field size can, and it's the physical cause.
# For reference: at 33%, MODIS needs ~47 acres; Sentinel-2 (10m, 0.025
# acres/pixel) clears both lines below an acre.
REFUSE_PIXEL_FRACTION = 0.33
DEGRADE_PIXEL_FRACTION = 0.10


def polygon_acres(boundary: dict) -> float:
    """Equirectangular projection at the polygon's own mean latitude, then a
    planar shoelace -- the same approach (and the same accuracy tradeoff)
    frontend/lib/geo.ts's polygonAcres() uses at save time, reimplemented
    here so a feature fetch doesn't need an extra Earth Engine round trip
    just to learn how big the field is. Well under 1% error at field scale."""
    ring = boundary["coordinates"][0]
    if len(ring) < 3:
        return 0.0
    earth_radius_m = 6378137.0
    mean_lat = sum(lat for _, lat in ring) / len(ring)
    cos_lat = math.cos(math.radians(mean_lat))
    projected = [(math.radians(lng) * earth_radius_m * cos_lat,
                  math.radians(lat) * earth_radius_m) for lng, lat in ring]
    twice_area = 0.0
    for i in range(len(projected)):
        x1, y1 = projected[i]
        x2, y2 = projected[(i + 1) % len(projected)]
        twice_area += x1 * y2 - x2 * y1
    return abs(twice_area) / 2 / M2_PER_ACRE


def field_coverage_tier(observed_acres: float, field_acres: float,
                         pixel_scale_m: float = None) -> str:
    """Confidence label for a FIELD-level NDVI signal
    (predict_live.coverage_tier is the county equivalent and stays as-is --
    it's calibrated to MODIS county counts the live county pipeline still
    depends on).

    The "unreliable" tier has no county analogue and is the important one.
    It keys off PIXEL SIZE RELATIVE TO THE FIELD, not off an observed/actual
    area ratio, because reduceRegion inherently over-counts edge pixels on
    any small polygon and the overhang grows with pixel size -- measured on
    the 18.8-acre test field below, a clean reading already returns 1.34x
    the true area at 10m, 1.39x at 30m and 1.65x at 250m. A fixed
    observed/actual ratio therefore cannot separate benign edge overhang
    from a sensor genuinely reading the neighbors; pixel-to-field size can,
    and is the physical cause of both.

    Why this matters concretely: that same 18.8-acre field (2025 CDL: 50.5%
    soybeans / 41.2% alfalfa / 0.9% corn) is spanned by only ~2 MODIS
    pixels, each 15.4 acres -- one pixel covers 82% of the whole field and
    spills well past its edges. MODIS duly reported 3 confident "corn"
    pixels at NDVI 0.82-0.89 on a field with a single 30m corn pixel in it,
    and showed flat 0.86-0.88 soybean NDVI all season where Sentinel-2
    correctly traced emergence (0.54 -> 0.88 -> 0.86). Calling that "low
    confidence" understates it: the number isn't imprecise, it's about
    different land."""
    if not observed_acres or observed_acres <= 0:
        return "none"

    coarse = False
    if field_acres and pixel_scale_m:
        pixel_fraction = (pixel_scale_m ** 2 / M2_PER_ACRE) / field_acres
        if pixel_fraction > REFUSE_PIXEL_FRACTION:
            return "unreliable"
        # Between the two lines the sensor is coarse relative to the field:
        # answer, but never claim better than "low" no matter how many
        # acres were observed.
        coarse = pixel_fraction > DEGRADE_PIXEL_FRACTION

    if coarse:
        return "low"
    if observed_acres >= COVERAGE_HIGH_ACRES:
        return "high"
    if observed_acres >= COVERAGE_MEDIUM_ACRES:
        return "medium"
    return "low"


def field_geometry_from_boundary(boundary: dict) -> ee.Geometry:
    """`boundary` is the GeoJSON Polygon shape frontend/lib/geo.ts's
    polygonToGeoJSON() produces and src/supabase_farm_schema.sql's
    `fields.boundary` stores -- {"type": "Polygon", "coordinates": [[[lng,
    lat], ...]]}. GeoJSON ring winding/closure is exactly what
    ee.Geometry.Polygon expects, so this is a direct pass-through."""
    return ee.Geometry.Polygon(boundary["coordinates"])


def field_county(geometry: ee.Geometry) -> dict:
    """Which county a field falls in, via a spatial join against the same
    TIGER/2018/Counties collection fetch_gee.py's county path already uses
    -- this is what lets Phase 3 (predict_field.py) apply the trained
    model's state one-hot encoding and look up a historical-yield
    comparison WITHOUT asking the farmer to pick their state by hand; a
    field polygon alone is enough. A field straddling two counties gets
    whichever one .first() returns (arbitrary) -- an edge case, not
    handled specially. A field outside all 3233 US counties (bad polygon,
    or geocoded to open water) comes back with every value None, which
    predict_field.py already treats as "unsupported region" since no
    known state_fips will match."""
    match = COUNTIES.filterBounds(geometry).first().getInfo()
    props = match.get("properties") or {}
    state_fips = props.get("STATEFP")
    county_fips = props.get("COUNTYFP")
    return {
        "state_fips": str(state_fips).zfill(2) if state_fips is not None else None,
        "county_fips": str(county_fips).zfill(3) if county_fips is not None else None,
        "county_name": props.get("NAME"),
    }


def field_crop_composition(geometry: ee.Geometry, cdl_year: int, top_n: int = 4) -> list:
    """What the Cropland Data Layer thinks is growing on this field, as
    [{code, acres, pct}, ...] sorted biggest first, at CDL's native 30m.

    Used to explain a coverage failure in terms the farmer can check
    against their own knowledge, rather than the opaque "not enough crop
    detected." CDL is published about a year late, so on any field that
    rotates it is describing LAST season -- when it disagrees with what the
    farmer told us, the farmer is right and this is the evidence of the
    mismatch, not a correction to them."""
    cdl = CDL.filter(ee.Filter.calendarRange(cdl_year, cdl_year, "year")).first().select("cropland")
    hist = cdl.reduceRegion(
        reducer=ee.Reducer.frequencyHistogram(),
        geometry=geometry,
        scale=30,
        maxPixels=1e9,
    ).getInfo().get("cropland") or {}
    total = sum(hist.values())
    if not total:
        return []
    rows = [
        {
            "cdl_code": int(code),
            "acres": count * 30 ** 2 / M2_PER_ACRE,
            "pct": 100 * count / total,
        }
        for code, count in hist.items()
    ]
    return sorted(rows, key=lambda r: -r["pct"])[:top_n]


def _fetch_static_features(geometry: ee.Geometry, field_id: str = None) -> dict:
    """Soil + terrain don't change season to season, so cache them per field
    (by field_id, if given) instead of re-hitting GEE every call. No cache
    without a field_id -- ad hoc/test polygons just fetch fresh each time."""
    cache_path = STATIC_CACHE_DIR / f"{field_id}.json" if field_id else None
    if cache_path and cache_path.exists():
        return json.loads(cache_path.read_text())

    features = {**fetch_field_soil(geometry), **fetch_field_terrain(geometry)}

    if cache_path:
        STATIC_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(features))
    return features


def fetch_field_features(boundary: dict, crop: str, as_of: date = None,
                          cdl_year: int = None, field_id: str = None) -> dict:
    """Builds one feature row for a single field, at whatever checkpoint the
    season's actually reached (same logic predict_live.py uses per county).
    Returns None if not enough of the season has elapsed for any checkpoint
    yet (mirrors predict_live.predict()'s early exit, but returns None
    instead of sys.exit(1) -- this is a library function, not a CLI)."""
    as_of = as_of or date.today()
    done = completed_periods(as_of, crop)
    checkpoint_name = pick_checkpoint(done, crop)
    if checkpoint_name is None:
        return None

    periods = crop_checkpoints(crop)[checkpoint_name]
    all_period_ranges = all_periods()
    geometry = field_geometry_from_boundary(boundary)
    cdl_code = CROPS[crop]["cdl_code"]
    cdl_year = cdl_year or latest_available_cdl_year()

    row = {
        "crop": crop,
        "year": as_of.year,
        "checkpoint": checkpoint_name,
        "cdl_year": cdl_year,
        **field_county(geometry),
    }

    needs_stress = (crop, checkpoint_name) in NEEDS_STRESS

    crop_pixel_counts = []
    pixel_scale_m = None
    for period_name in periods:
        start_md, end_md = all_period_ranges[period_name]

        ndvi = fetch_period_ndvi_for_field(geometry, as_of.year, period_name, start_md, end_md,
                                            cdl_code, cdl_year=cdl_year)
        row[f"ndvi_{period_name}"] = ndvi["ndvi_mean"]
        crop_pixel_counts.append(ndvi["crop_pixel_count"] or 0)
        pixel_scale_m = ndvi["pixel_scale_m"]

        weather = fetch_period_weather_for_field(geometry, as_of.year, period_name, start_md, end_md)
        row[f"precip_sum_{period_name}"] = weather["precip_sum_mm"]
        row[f"tmean_{period_name}"] = weather["tmean_c"]
        row[f"tmax_{period_name}"] = weather["tmax_c"]
        row[f"tmin_{period_name}"] = weather["tmin_c"]

        moisture = fetch_period_soil_moisture_for_field(geometry, as_of.year, period_name, start_md, end_md)
        row[f"soil_moisture_{period_name}"] = moisture["soil_moisture_vol"]

        # Only fetched for the (crop, checkpoint) combos that actually
        # trained on these columns (see build_dataset.NEEDS_STRESS) -- an
        # extra GEE round trip per period isn't worth paying on every
        # single-field on-demand prediction when most checkpoints ignore it.
        if needs_stress:
            stress = fetch_period_stress_for_field(geometry, as_of.year, period_name, start_md, end_md)
            for metric in STRESS_METRICS:
                row[f"{metric}_{period_name}"] = stress[metric]

    # Weakest-link pixel count across periods, same coverage/confidence
    # signal predict_live.fetch_current_ndvi uses -- see this module's
    # docstring on why it'll typically be much smaller than a county's.
    row["crop_pixel_coverage"] = min(crop_pixel_counts) if crop_pixel_counts else 0

    # ...but pixel COUNT is sensor-dependent, so the tier that a farmer
    # actually sees is computed from observed ACRES instead (see
    # field_coverage_tier). Both are kept: the count still feeds the model
    # as a feature (it's what the model was trained on), while the acreage
    # is what the confidence label and the contamination check use.
    row["crop_pixel_scale_m"] = pixel_scale_m
    row["field_acres"] = polygon_acres(boundary)
    row["crop_observed_acres"] = (
        row["crop_pixel_coverage"] * pixel_scale_m ** 2 / M2_PER_ACRE if pixel_scale_m else None
    )

    row.update(_fetch_static_features(geometry, field_id))

    rotation = fetch_field_rotation(geometry, cdl_year, cdl_code)
    row["pct_continuous"] = rotation["pct_continuous"]
    row["rotation_pixel_count"] = rotation["rotation_pixel_count"]

    return row


if __name__ == "__main__":
    import sys

    # Demo polygon: a ~40-acre square near Ames, IA, so this is runnable
    # ad hoc without a real Supabase field row. Real usage passes a field's
    # actual `boundary` (and its id, for static-feature caching).
    demo_boundary = {
        "type": "Polygon",
        "coordinates": [[
            [-93.62, 41.99], [-93.61, 41.99], [-93.61, 41.98], [-93.62, 41.98], [-93.62, 41.99],
        ]],
    }
    crop = sys.argv[1] if len(sys.argv) > 1 else "corn"
    print(f"Fetching field-level features for crop={crop}, demo polygon near Ames, IA...")
    result = fetch_field_features(demo_boundary, crop)
    if result is None:
        print("Not enough of the season has elapsed for any checkpoint yet.")
    else:
        for key, value in result.items():
            print(f"  {key}: {value}")
