"""Backtest of stage_projection.project_stage_windows() against real past
seasons, run BEFORE the calendar shows any projected date (same
validate-then-ship discipline as evaluate_stress_features.py).

Leave-one-year-out: for each held-out year, pretend it is `lead_days` after
planting, project every remaining stage from the OTHER years only, then
compare against the date that year actually reached the stage.

Reports per crop/stage/lead: median absolute error (days), bias (days,
+ = projected later than actual) and coverage (share of actual dates that
fell inside the early-late window, ideally near 50% for a quartile window).

Usage: python src/backtest_stage_projection.py
"""
import sys
from datetime import date, timedelta
from pathlib import Path
from statistics import mean, median

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gee_auth import ensure_initialized
from growth_stages import CROP_STAGE_MODELS
from stage_projection import project_stage_windows

# Story County, IA -- a small square, the centroid is what gets sampled.
BOUNDARY = {"type": "Polygon", "coordinates": [[
    [-93.48, 42.02], [-93.46, 42.02], [-93.46, 42.04], [-93.48, 42.04], [-93.48, 42.02]]]}
PLANTING = {"corn": (5, 10), "soybeans": (5, 20)}
LEADS = (30, 60)  # days after planting the projection is made
YEARS = list(range(2005, 2026))


def actual_date(rows, planting: date, threshold: float):
    cumulative = 0.0
    for r in rows:
        d = date.fromisoformat(r["date"])
        if d < planting:
            continue
        cumulative += r["gdu"]
        if cumulative >= threshold:
            return d
    return None


def main():
    ensure_initialized()
    from fetch_prism import fetch_field_daily_gdu
    from fetch_field_features import field_geometry_from_boundary

    geometry = field_geometry_from_boundary(BOUNDARY)
    print(f"{'crop':9} {'stage':5} {'lead':>4} {'n':>3} {'MAE d':>6} {'bias d':>7} {'in window':>10}")
    for crop, (month, day) in PLANTING.items():
        model = CROP_STAGE_MODELS[crop]
        # Earth Engine aborts getInfo() past 5000 elements (~13 years of daily
        # rows), so fetch in chunks; production's 8-year window fits in one.
        daily = []
        for i in range(0, len(YEARS), 8):
            chunk = YEARS[i:i + 8]
            daily += fetch_field_daily_gdu(geometry, f"{chunk[0]}-01-01", f"{chunk[-1]}-12-31",
                                           base_f=model["base_f"], cap_f=model["cap_f"])
        by_year = {}
        for r in daily:
            if r["gdu"] is not None:
                by_year.setdefault(int(r["date"][:4]), []).append(r)
        for lead in LEADS:
            errors = {}
            for held_out in YEARS:
                rows = sorted(by_year.get(held_out, []), key=lambda r: r["date"])
                planting = date(held_out, month, day)
                as_of = planting + timedelta(days=lead)
                accumulated = sum(r["gdu"] for r in rows if planting <= date.fromisoformat(r["date"]) < as_of)
                others = [y for y in YEARS if y != held_out]
                proj = project_stage_windows(daily, as_of, accumulated, model["stages"], others)
                for threshold, code, _ in model["stages"]:
                    p = proj.get(code)
                    if not p or p["likely"] is None:
                        continue
                    actual = actual_date(rows, planting, threshold)
                    if actual is None:
                        continue
                    err = (date.fromisoformat(p["likely"]) - actual).days
                    inside = date.fromisoformat(p["from"]) <= actual <= date.fromisoformat(p["to"])
                    errors.setdefault(code, []).append((err, inside))
            for code, vals in errors.items():
                errs = [v[0] for v in vals]
                print(f"{crop:9} {code:5} {lead:>4} {len(vals):>3} {median(abs(e) for e in errs):>6.1f} "
                      f"{mean(errs):>7.1f} {sum(v[1] for v in vals) / len(vals):>9.0%}")


if __name__ == "__main__":
    main()
