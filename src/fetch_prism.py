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

from config import STATE_FIPS, YEAR_START, YEAR_END, all_periods

from gee_auth import ensure_initialized
ensure_initialized()

COUNTIES = ee.FeatureCollection("TIGER/2018/Counties")
PRISM = ee.ImageCollection("OREGONSTATE/PRISM/ANd")


def fetch_field_gdd(geometry, planting_date: str, as_of_date: str,
                     base_f: float = 50.0, cap_f: float = 86.0) -> dict:
    """Growing Degree Units accumulated over a field from planting to date.

    Agronomy Layer 1 (see ../ARCHITECTURE.md). GDU is the standard
    heat-accumulation measure crop development actually tracks:
    daily = (min(Tmax, cap) + max(Tmin, base)) / 2 - base, floored at zero,
    summed from the planting date the farmer gave us.

    Computed server-side as one summed collection, so this is a single
    round trip regardless of how many days the window covers.

    Note on scale: PRISM is a 4km grid, so this is a genuinely regional
    temperature signal rather than a field-specific one -- and that is
    honest rather than a limitation, because air temperature really doesn't
    vary meaningfully across one field. It also means GDD staging works
    identically on a 15-acre field and a 500-acre one, unlike NDVI, which
    is where the small-field resolution problem lives.

    PRISM bands are Celsius; the base/cap thresholds are the Fahrenheit
    values agronomic literature publishes, so conversion happens here.
    """
    days = PRISM.filterDate(planting_date, as_of_date)

    def _daily_gdu(image):
        tmax_f = image.select("tmax").multiply(9 / 5).add(32).min(cap_f)
        tmin_f = image.select("tmin").multiply(9 / 5).add(32).max(base_f)
        return tmax_f.add(tmin_f).divide(2).subtract(base_f).max(0).rename("gdu")

    total = days.map(_daily_gdu).sum()
    stats = total.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=geometry,
        scale=4000,
        maxPixels=1e9,
    ).getInfo()

    return {
        "accumulated_gdd": stats.get("gdu"),
        "planting_date": planting_date,
        "as_of_date": as_of_date,
        "base_f": base_f,
        "cap_f": cap_f,
    }


def fetch_period_stress(state_fips_list: list, year_start: int, year_end: int,
                         period_name: str, start_md: str, end_md: str) -> pd.DataFrame:
    """Agronomy Layer 2 (see ../ARCHITECTURE.md): threshold-and-count stress
    metrics per county per period, instead of only monthly means.

    Why these specific metrics rather than a monthly average: crop damage is
    NONLINEAR in temperature. Schlenker & Roberts (2009, PNAS) is the
    canonical result -- US corn yields rise gently with heat up to roughly
    29C and then fall sharply above it, so a month averaging 24C with three
    days at 36C and a month steady at 24C are agronomically very different
    and numerically identical in `tmean`. Encoding the threshold directly
    hands the model a known mechanism instead of asking it to rediscover a
    kink from limited county-year data.

    Metrics:
      edd_29c        Extreme (killing) degree days -- sum of daily
                     max(0, Tmax - 29C). The Schlenker & Roberts measure.
      days_above_30c / days_above_35c
                     Plain counts, easier to reason about than EDD and a
                     different shape of the same signal (35C is the severe
                     tail, rare but very damaging during pollination).
      gdd_10_30c     Beneficial heat over the same window (base 10C, capped
                     30C), so the model can separate "warm and good" from
                     "hot and damaging" rather than conflating them in tmean.
      dry_days       Days with < 1mm precipitation -- distribution, not just
                     the monthly total. 100mm in one storm and 100mm spread
                     over the month are the same `precip_sum_mm` and very
                     different for the crop.
      heavy_rain_days
                     Days over 25mm -- excess moisture / runoff signal.

    Not included: longest CONSECUTIVE dry spell, which is agronomically
    better than a plain dry-day count but needs sequential state that
    Earth Engine's per-image map can't express cheaply. Worth revisiting
    with a different formulation rather than faked with a proxy.
    """
    counties = COUNTIES.filter(ee.Filter.inList("STATEFP", state_fips_list))
    rows = []
    for year in range(year_start, year_end + 1):
        days = PRISM.filterDate(f"{year}-{start_md}", f"{year}-{end_md}")

        edd = days.map(lambda i: i.select("tmax").subtract(29).max(0)).sum().rename("edd_29c")
        gdd = days.map(
            lambda i: i.select("tmax").min(30).add(i.select("tmin").max(10)).divide(2).subtract(10).max(0)
        ).sum().rename("gdd_10_30c")
        hot30 = days.map(lambda i: i.select("tmax").gt(30)).sum().rename("days_above_30c")
        hot35 = days.map(lambda i: i.select("tmax").gt(35)).sum().rename("days_above_35c")
        dry = days.map(lambda i: i.select("ppt").lt(1)).sum().rename("dry_days")
        wet = days.map(lambda i: i.select("ppt").gt(25)).sum().rename("heavy_rain_days")

        combined = edd.addBands([gdd, hot30, hot35, dry, wet])
        stats = combined.reduceRegions(collection=counties, reducer=ee.Reducer.mean(), scale=4000)
        for f in stats.getInfo()["features"]:
            props = f["properties"]
            rows.append({
                "year": year,
                "period": period_name,
                "state_fips": props.get("STATEFP"),
                "county_fips": props.get("COUNTYFP"),
                "county_name": props.get("NAME"),
                "edd_29c": props.get("edd_29c"),
                "gdd_10_30c": props.get("gdd_10_30c"),
                "days_above_30c": props.get("days_above_30c"),
                "days_above_35c": props.get("days_above_35c"),
                "dry_days": props.get("dry_days"),
                "heavy_rain_days": props.get("heavy_rain_days"),
            })
        print(f"  [stress {period_name}] fetched {year}: {len(rows)} rows so far")
    return pd.DataFrame(rows)


def fetch_period_stress_for_field(geometry: ee.Geometry, year: int, period_name: str,
                                   start_md: str, end_md: str) -> dict:
    """Same Layer 2 threshold metrics as fetch_period_stress, reduced over a
    single field polygon (reduceRegion) instead of every county
    (reduceRegions) -- the field-level analog of fetch_period_weather_for_field.
    Only called for the (crop, checkpoint) combos in build_dataset.NEEDS_STRESS,
    since that's the only place the trained model actually expects these
    columns; everywhere else fetching them would just be wasted latency on
    an interactive, on-demand endpoint."""
    start = f"{year}-{start_md}"
    end = f"{year}-{end_md}"
    days = PRISM.filterDate(start, end)

    edd = days.map(lambda i: i.select("tmax").subtract(29).max(0)).sum().rename("edd_29c")
    gdd = days.map(
        lambda i: i.select("tmax").min(30).add(i.select("tmin").max(10)).divide(2).subtract(10).max(0)
    ).sum().rename("gdd_10_30c")
    hot30 = days.map(lambda i: i.select("tmax").gt(30)).sum().rename("days_above_30c")
    hot35 = days.map(lambda i: i.select("tmax").gt(35)).sum().rename("days_above_35c")
    dry = days.map(lambda i: i.select("ppt").lt(1)).sum().rename("dry_days")
    wet = days.map(lambda i: i.select("ppt").gt(25)).sum().rename("heavy_rain_days")

    combined = edd.addBands([gdd, hot30, hot35, dry, wet])
    stats = combined.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=geometry,
        scale=4000,
        maxPixels=1e9,
    ).getInfo()
    return {
        "edd_29c": stats.get("edd_29c"),
        "gdd_10_30c": stats.get("gdd_10_30c"),
        "days_above_30c": stats.get("days_above_30c"),
        "days_above_35c": stats.get("days_above_35c"),
        "dry_days": stats.get("dry_days"),
        "heavy_rain_days": stats.get("heavy_rain_days"),
    }


def fetch_field_daily_gdu(geometry, start_date: str, end_date: str,
                           base_f: float = 50.0, cap_f: float = 86.0) -> list:
    """Per-day GDU over a field for a whole date range, as
    [{"date": "YYYY-MM-DD", "gdu": float}, ...].

    One Earth Engine round trip for the entire range, however many years it
    spans -- the per-day reduction is mapped server-side and only the
    resulting numbers come back. That's what makes the multi-year
    same-growth-stage comparison in field_insights.py affordable; doing it
    with one call per day would be hundreds of round trips.

    Sampled at the field's CENTROID rather than reduced over the whole
    polygon: PRISM is a 4km grid, so a field of any realistic size sits
    inside one or two cells and the centroid value is the same number a
    polygon mean would return -- but a point sample is dramatically cheaper
    across the ~1800 daily images a multi-year range contains, which is the
    difference between this being usable behind a request and not.

    fetch_field_gdd() above answers "how much heat since planting"; this
    answers "on which date had X heat accumulated", which is what lets a
    prior season be sampled at the same development point rather than the
    same calendar week."""
    point = ee.Geometry(geometry).centroid(maxError=1)
    daily = PRISM.filterDate(start_date, end_date)

    def _to_feature(image):
        tmax_f = image.select("tmax").multiply(9 / 5).add(32).min(cap_f)
        tmin_f = image.select("tmin").multiply(9 / 5).add(32).max(base_f)
        gdu = tmax_f.add(tmin_f).divide(2).subtract(base_f).max(0).rename("gdu")
        value = gdu.reduceRegion(
            reducer=ee.Reducer.first(), geometry=point, scale=4000, maxPixels=1e9
        ).get("gdu")
        return ee.Feature(None, {"date": image.date().format("YYYY-MM-dd"), "gdu": value})

    features = daily.map(_to_feature).getInfo()["features"]
    return [
        {"date": f["properties"]["date"], "gdu": f["properties"].get("gdu")}
        for f in features
    ]


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


def fetch_period_weather_for_field(geometry: ee.Geometry, year: int, period_name: str,
                                    start_md: str, end_md: str) -> dict:
    """Same PRISM weather as fetch_period_weather, reduced over a single
    field polygon (reduceRegion) instead of every county (reduceRegions).
    PRISM is a 4km grid -- unlike NDVI's 250m, a field usually sits well
    inside one or two PRISM cells, so this is closer to "the weather at
    this field" than NDVI's per-field pixel count ever will be."""
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

    # Multi-band image + single (non-combined) reducer -> EE keys the output
    # by band name directly, same convention the county path relies on.
    stats = combined.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=geometry,
        scale=4000,
        maxPixels=1e9,
    ).getInfo()
    return {
        "year": year,
        "period": period_name,
        "precip_sum_mm": stats.get("precip_sum_mm"),
        "tmean_c": stats.get("tmean_c"),
        "tmax_c": stats.get("tmax_c"),
        "tmin_c": stats.get("tmin_c"),
    }


if __name__ == "__main__":
    import sys

    # `python src/fetch_prism.py stress` pulls the Layer 2 threshold metrics
    # into their own file, leaving the original weather pull untouched so
    # the two can be re-run independently.
    mode = sys.argv[1] if len(sys.argv) > 1 else "weather"
    fetcher, out_path = {
        "weather": (fetch_period_weather, "data/raw/prism_weather_periods.csv"),
        "stress": (fetch_period_stress, "data/raw/prism_stress_periods.csv"),
    }[mode]

    frames = []
    for period_name, (start_md, end_md) in all_periods().items():
        print(f"Period: {period_name} ({start_md} to {end_md})")
        frames.append(fetcher(STATE_FIPS, YEAR_START, YEAR_END, period_name, start_md, end_md))
    df = pd.concat(frames, ignore_index=True)
    df.to_csv(out_path, index=False)
    print(f"Saved {len(df)} rows to {out_path}")
