"""The small-farm monitoring product (see ARCHITECTURE.md, "What a small
farm can actually be told").

Deliberately SEPARATE from predict_field.py. That module answers "what will
this field yield?", which requires imagery fine enough to resolve the field
and therefore refuses on anything under roughly 150 acres with today's
MODIS-based path. The insights here are the things that stay reliable at
any field size, so they must not be gated behind a prediction that will
often, correctly, decline to exist.

Growth stage is the first of them and the clearest case: it comes from
accumulated temperature (PRISM, 4km), and air temperature genuinely doesn't
vary across a single field, so a 15-acre field gets exactly the same
quality of answer as a 500-acre one. No resolution problem, no sensor
calibration problem, no county model in the path.
"""
import statistics
from datetime import date, timedelta

import ee

from fetch_prism import fetch_field_gdd, fetch_field_daily_gdu
from fetch_gee import _s2_ndvi_composite
from fetch_field_features import field_geometry_from_boundary
from growth_stages import stage_for_gdd, stage_model

# Sentinel-2's dual-satellite record; before this the revisit rate is too
# sparse for a reliable short-window composite (see ARCHITECTURE.md 4a).
S2_FIRST_GOOD_YEAR = 2018

# Half-widths tried, in order, for the composite centred on each year's
# equivalent growth-stage date. Widening is adaptive rather than fixed
# because cloud cover genuinely empties narrow windows -- +/-7 days
# returned zero usable pixels for September 2026 on the test field while
# +/-14 returned 12,656. Start tight to keep the "same stage" comparison
# honest, widen only as far as needed to get a measurement at all, and
# report which width was used so a loosened comparison is visible rather
# than silent.
STAGE_WINDOW_DAYS = (7, 14, 21)


def field_growth_stage(boundary: dict, crop: str, planting_date: str,
                        as_of: date = None) -> dict:
    """Where this field's crop is in its development, from the farmer's own
    planting date plus accumulated heat since.

    Failure modes come back as {"error": ..., "message": ...} rather than
    raising, matching predict_field.py's contract, since this sits directly
    behind an API endpoint."""
    as_of = as_of or date.today()

    if not planting_date:
        return {
            "error": "no_planting_date",
            "message": "Add this field's planting date to see its growth stage -- "
                       "development tracks accumulated heat from planting, so we can't "
                       "place the crop in its season without it.",
        }

    model = stage_model(crop)
    if model is None:
        return {
            "error": "no_stage_model",
            "message": f"We don't have a defensible growth-stage model for {crop} yet. "
                       f"Winter wheat is fall-planted and overwinters, so heat accumulated "
                       f"since planting spans a dormant period and doesn't describe "
                       f"development the way it does for a spring-planted crop.",
        }

    # Postgres `date` accepts years far outside anything meaningful here
    # (up to 294276), and a segmented <input type="date"> will happily emit
    # a 6-digit year if someone types into the wrong segment -- which is
    # exactly how '122026-05-12' reached the database during testing. Parse
    # defensively and reject politely rather than 500ing on it.
    try:
        planting = date.fromisoformat(planting_date)
    except (ValueError, TypeError):
        return {
            "error": "invalid_planting_date",
            "message": f"'{planting_date}' isn't a date we can read. Please re-enter this "
                       f"field's planting date.",
        }
    if not (as_of.year - 2 <= planting.year <= as_of.year + 1):
        return {
            "error": "invalid_planting_date",
            "message": f"A planting date of {planting_date} isn't in a plausible range for the "
                       f"current season. Please re-enter it.",
        }
    if planting > as_of:
        return {
            "error": "planting_in_future",
            "message": f"This field's planting date ({planting_date}) is in the future, "
                       f"so there's no growing season to report on yet.",
        }

    gdd = fetch_field_gdd(
        field_geometry_from_boundary(boundary),
        planting_date,
        as_of.isoformat(),
        base_f=model["base_f"],
        cap_f=model["cap_f"],
    )
    staged = stage_for_gdd(crop, gdd["accumulated_gdd"])
    if staged is None or staged["accumulated_gdd"] is None:
        return {
            "error": "no_temperature_data",
            "message": "No temperature data came back for this field and date range.",
        }

    return {
        "crop": crop,
        "planting_date": planting_date,
        "as_of": as_of.isoformat(),
        "days_since_planting": (as_of - planting).days,
        **staged,
    }


def _equivalent_stage_dates(daily_gdu: list, planting_month_day: str, years: list,
                             target_gdd: float) -> dict:
    """For each year, the date on which this field had accumulated
    `target_gdd` since that year's assumed planting -- i.e. the date that
    year was at the SAME development point the field is at now.

    APPROXIMATION, stated rather than hidden: prior seasons are assumed to
    have been planted on the same month/day as this one, because we only
    have the farmer's planting date for the current season. That's much
    closer than comparing calendar dates (it still absorbs each year's own
    temperature history, which is the dominant term) but a year the farmer
    genuinely planted three weeks earlier will be sampled somewhat off.
    Collecting planting dates each season fixes this permanently."""
    by_year = {}
    for row in daily_gdu:
        if row["gdu"] is None:
            continue
        by_year.setdefault(row["date"][:4], []).append(row)

    equivalents = {}
    for year in years:
        rows = sorted(by_year.get(str(year), []), key=lambda r: r["date"])
        planting = f"{year}-{planting_month_day}"
        cumulative = 0.0
        reached = None
        for row in rows:
            if row["date"] < planting:
                continue
            cumulative += row["gdu"]
            if cumulative >= target_gdd:
                reached = row["date"]
                break
        # None means this year never got this warm this far into the season
        # -- a real answer (a cold year), not a gap to paper over.
        equivalents[year] = {"date": reached, "gdd_at_end": cumulative}
    return equivalents


def _field_ndvi_window(geometry, center_date: str, windows=STAGE_WINDOW_DAYS) -> dict:
    """Whole-field Sentinel-2 NDVI over a window centred on a date, widening
    the window until the composite actually contains pixels.

    No crop mask, deliberately: the farmer has told us what's planted, so
    masking to CDL's year-late guess would only reintroduce the error 4b
    removed -- and on a small or mixed field the mask throws away most of
    the pixels that make this measurement reliable in the first place."""
    center = date.fromisoformat(center_date)
    for days in windows:
        start = (center - timedelta(days=days)).isoformat()
        end = (center + timedelta(days=days)).isoformat()
        ndvi = _s2_ndvi_composite(start, end, geometry)
        stats = ndvi.reduceRegion(
            reducer=ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True),
            geometry=geometry,
            scale=10,
            maxPixels=1e9,
        ).getInfo()
        if stats.get("NDVI_count"):
            return {
                "center_date": center_date,
                "ndvi": stats.get("NDVI_mean"),
                "pixels": stats.get("NDVI_count"),
                "window_days": days,
            }
    # Every width came back empty -- persistent cloud over this field for
    # roughly six weeks around this date. A real answer, not a bug.
    return {"center_date": center_date, "ndvi": None, "pixels": 0,
            "window_days": max(windows)}


def field_stage_benchmark(boundary: dict, crop: str, planting_date: str,
                           as_of: date = None, years_back: int = 5) -> dict:
    """How this field's canopy compares to ITSELF in prior seasons, sampled
    at the same growth stage rather than the same calendar week.

    This is the small-farm product (see ARCHITECTURE.md). It works at any
    field size because it never leaves Sentinel-2: same sensor, same
    polygon, same masking, so the cross-sensor calibration problem that
    sank the MODIS/Sentinel-2 reconciliation simply doesn't arise. And it
    produces something a farmer can act on -- "well behind where this field
    normally is at this stage" -- for fields the yield model must refuse."""
    as_of = as_of or date.today()
    current = field_growth_stage(boundary, crop, planting_date, as_of)
    if "error" in current:
        return current

    geometry = field_geometry_from_boundary(boundary)
    target_gdd = current["accumulated_gdd"]
    planting_month_day = planting_date[5:]

    prior_years = [y for y in range(as_of.year - years_back, as_of.year)
                    if y >= S2_FIRST_GOOD_YEAR]
    if not prior_years:
        return {"error": "no_history",
                "message": "No prior seasons with usable satellite imagery to compare against yet."}

    model = stage_model(crop)
    daily = fetch_field_daily_gdu(
        geometry,
        f"{min(prior_years)}-01-01",
        f"{max(prior_years)}-12-31",
        base_f=model["base_f"],
        cap_f=model["cap_f"],
    )
    equivalents = _equivalent_stage_dates(daily, planting_month_day, prior_years, target_gdd)

    history = []
    for year in prior_years:
        equivalent_date = equivalents[year]["date"]
        if equivalent_date is None:
            history.append({"year": year, "equivalent_date": None, "ndvi": None,
                             "note": "this field never accumulated that much heat in this season"})
            continue
        measurement = _field_ndvi_window(geometry, equivalent_date)
        history.append({"year": year, "equivalent_date": equivalent_date,
                         "ndvi": measurement["ndvi"], "pixels": measurement["pixels"],
                         "window_days": measurement["window_days"]})

    now = _field_ndvi_window(geometry, as_of.isoformat())
    comparable = [h["ndvi"] for h in history if h["ndvi"] is not None]

    result = {
        "crop": crop,
        "planting_date": planting_date,
        "as_of": as_of.isoformat(),
        "stage": current["stage"],
        "accumulated_gdd": target_gdd,
        "current_ndvi": now["ndvi"],
        "current_pixels": now["pixels"],
        "current_window_days": now["window_days"],
        "history": history,
        "comparison_basis": "same growth stage (equal accumulated heat), not same calendar date",
        "planting_assumption": "prior seasons assumed planted on the same month/day as this one",
    }

    if now["ndvi"] is None or len(comparable) < 2:
        result["verdict"] = None
        result["message"] = ("Not enough clear satellite history yet to say how this season "
                              "compares -- this builds up as the field accumulates seasons.")
        return result

    mean = statistics.mean(comparable)
    result["history_mean_ndvi"] = mean
    result["pct_vs_history"] = 100 * (now["ndvi"] - mean) / mean
    if len(comparable) >= 3:
        sd = statistics.stdev(comparable)
        result["history_sd_ndvi"] = sd
        result["sd_from_history"] = (now["ndvi"] - mean) / sd if sd else None
    return result


if __name__ == "__main__":
    import sys

    demo_boundary = {
        "type": "Polygon",
        "coordinates": [[
            [-93.62, 41.99], [-93.61, 41.99], [-93.61, 41.98], [-93.62, 41.98], [-93.62, 41.99],
        ]],
    }
    crop = sys.argv[1] if len(sys.argv) > 1 else "corn"
    planting = sys.argv[2] if len(sys.argv) > 2 else "2026-05-12"
    result = field_growth_stage(demo_boundary, crop, planting)
    for key, value in result.items():
        print(f"  {key}: {value}")
