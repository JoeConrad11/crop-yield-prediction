"""Forward projection of crop growth-stage dates for the farm calendar
(see ../ARCHITECTURE.md, "Future: the field calendar").

"At your accumulated heat, this field reaches pollination in roughly 9-14
days" -- derived from THIS field's accumulated GDD plus what past seasons'
weather did from this same point on the calendar, never a hardcoded date.

Method (climate-analog, no forecast): for each prior year, start at today's
month/day and count how many days that year took to accumulate the heat
still needed to reach a stage. The spread across years is the window:
25th percentile = early, median = likely, 75th percentile = late. Warm
years run early, cold years late, and the honest output is that range, not
a single day.

The math (project_stage_windows) is pure and takes already-fetched daily
GDU, so it is unit-testable and backtestable without Earth Engine. Only
field_stage_projection() touches EE, through the same fetch_field_daily_gdu()
the same-stage benchmark already uses.

Refuses rather than guesses: fewer than MIN_YEARS usable prior seasons for a
stage means no window for that stage, and crops without a staging model
(winter wheat, see growth_stages.py) get none at all.
"""
import statistics
from datetime import date, timedelta

MIN_YEARS = 5


def _same_day(year: int, as_of: date) -> date:
    try:
        return date(year, as_of.month, as_of.day)
    except ValueError:  # Feb 29 in a non-leap year
        return date(year, as_of.month, 28)


def _days_to_accumulate(rows: list, start: date, needed: float):
    """Days after `start` (>= 1) until cumulative GDU reaches `needed`, or
    None if this year's data ends first."""
    cumulative = 0.0
    for row in rows:
        row_date = date.fromisoformat(row["date"])
        if row_date < start:
            continue
        cumulative += row["gdu"]
        if cumulative >= needed:
            return (row_date - start).days + 1
    return None


def project_stage_windows(daily_gdu: list, as_of: date, accumulated_gdd: float,
                          stages: list, years: list, min_years: int = MIN_YEARS) -> dict:
    """{stage_code: {...}} for every stage still ahead of `accumulated_gdd`.

    `daily_gdu`: [{"date": "YYYY-MM-DD", "gdu": float|None}, ...] covering
    `years`. `stages`: growth_stages-style (threshold, code, description)
    tuples. Stages already reached are omitted; stages with too few usable
    years come back with a `None` window and a reason, never a guess.
    """
    by_year = {}
    for row in daily_gdu:
        if row["gdu"] is None:
            continue
        by_year.setdefault(int(row["date"][:4]), []).append(row)
    for rows in by_year.values():
        rows.sort(key=lambda r: r["date"])

    out = {}
    for threshold, code, description in stages:
        needed = threshold - accumulated_gdd
        if needed <= 0:
            continue
        days = []
        for year in years:
            got = _days_to_accumulate(by_year.get(year, []), _same_day(year, as_of), needed)
            if got is not None:
                days.append(got)
        entry = {"description": description, "gdd_away": round(needed, 1), "years_used": len(days)}
        if len(days) < min_years:
            entry.update({"from": None, "likely": None, "to": None,
                          "reason": f"only {len(days)} prior season(s) reached this stage from this point"})
        else:
            q1, median, q3 = statistics.quantiles(days, n=4, method="inclusive")
            entry.update({
                "from": (as_of + timedelta(days=round(q1))).isoformat(),
                "likely": (as_of + timedelta(days=round(median))).isoformat(),
                "to": (as_of + timedelta(days=round(q3))).isoformat(),
                "reason": None,
            })
        out[code] = entry
    return out


def field_stage_projection(boundary: dict, crop: str, planting_date: str,
                           as_of: date = None, years_back: int = 8) -> dict:
    """Projected dates for this field's remaining growth stages. Errors come
    back as {"error", "message"} like field_growth_stage(), which this wraps
    (so it inherits its planting-date / no-model / no-data refusals)."""
    from fetch_prism import fetch_field_daily_gdu
    from field_insights import field_growth_stage
    from fetch_field_features import field_geometry_from_boundary
    from growth_stages import stage_model

    as_of = as_of or date.today()
    staged = field_growth_stage(boundary, crop, planting_date, as_of)
    if "error" in staged:
        return staged

    model = stage_model(crop)
    years = list(range(as_of.year - years_back, as_of.year))
    daily = fetch_field_daily_gdu(
        field_geometry_from_boundary(boundary),
        f"{years[0]}-01-01", f"{years[-1]}-12-31",
        base_f=model["base_f"], cap_f=model["cap_f"],
    )
    return {
        "crop": crop,
        "as_of": as_of.isoformat(),
        "accumulated_gdd": staged["accumulated_gdd"],
        "current_stage": staged["stage"],
        "stages": project_stage_windows(daily, as_of, staged["accumulated_gdd"],
                                        model["stages"], years),
        "confidence": model["confidence"],
        "caveat": model["caveat"],
        "method": f"Climate analog: the spread of {len(years)} prior seasons' heat from this "
                  f"date onward. Not a weather forecast.",
    }
