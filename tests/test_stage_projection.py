"""Pure projection math (no Earth Engine): climate-analog windows, refusal
with too little history, already-reached stages omitted."""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from stage_projection import MIN_YEARS, project_stage_windows

AS_OF = date(2026, 6, 1)
YEARS = list(range(2016, 2026))  # 10 prior seasons


def daily(years, gdu_for_year):
    rows = []
    for y in years:
        d = date(y, 1, 1)
        while d.year == y:
            rows.append({"date": d.isoformat(), "gdu": gdu_for_year(y)})
            d += timedelta(days=1)
    return rows


STAGES = [(100, "VE", "emergence"), (300, "V4", "4 leaf")]


def test_constant_heat_gives_a_point_window():
    out = project_stage_windows(daily(YEARS, lambda y: 10.0), AS_OF, 0.0, STAGES, YEARS)
    ve = out["VE"]
    assert ve["gdd_away"] == 100.0 and ve["years_used"] == 10
    # 100 GDU at 10/day -> 10 days
    assert ve["from"] == ve["likely"] == ve["to"] == (AS_OF + timedelta(days=10)).isoformat()
    assert out["V4"]["likely"] == (AS_OF + timedelta(days=30)).isoformat()


def test_warm_and_cold_years_widen_the_window():
    # half the years accumulate 20/day (5 days to 100), half 10/day (10 days)
    out = project_stage_windows(daily(YEARS, lambda y: 20.0 if y % 2 else 10.0), AS_OF, 0.0, STAGES, YEARS)
    ve = out["VE"]
    assert ve["from"] < ve["likely"] < ve["to"]
    assert ve["from"] >= (AS_OF + timedelta(days=5)).isoformat()
    assert ve["to"] <= (AS_OF + timedelta(days=10)).isoformat()


def test_accumulated_heat_shortens_the_wait():
    out = project_stage_windows(daily(YEARS, lambda y: 10.0), AS_OF, 60.0, STAGES, YEARS)
    assert out["VE"]["gdd_away"] == 40.0
    assert out["VE"]["likely"] == (AS_OF + timedelta(days=4)).isoformat()


def test_already_reached_stages_are_omitted():
    out = project_stage_windows(daily(YEARS, lambda y: 10.0), AS_OF, 150.0, STAGES, YEARS)
    assert "VE" not in out and "V4" in out


def test_too_few_years_refuses_instead_of_guessing():
    few = YEARS[: MIN_YEARS - 1]
    out = project_stage_windows(daily(few, lambda y: 10.0), AS_OF, 0.0, STAGES, few)
    assert out["VE"]["likely"] is None and out["VE"]["reason"]


def test_years_whose_data_ends_early_are_not_counted():
    # stage needs 2000 GDU (200 days at 10/day) -> Jun 1 + 200d = Dec 18, but
    # data for every year ends Dec 31 so it IS reachable; ask for 5000 instead
    out = project_stage_windows(daily(YEARS, lambda y: 10.0), AS_OF, 0.0, [(5000, "X", "far")], YEARS)
    assert out["X"]["years_used"] == 0 and out["X"]["likely"] is None


def test_none_gdu_rows_are_skipped():
    rows = daily(YEARS, lambda y: 10.0)
    for r in rows[:50]:
        r["gdu"] = None
    out = project_stage_windows(rows, AS_OF, 0.0, STAGES, YEARS)
    assert out["VE"]["years_used"] >= MIN_YEARS


def test_leap_day_as_of_does_not_crash():
    out = project_stage_windows(daily(YEARS, lambda y: 10.0), date(2024, 2, 29), 0.0, STAGES, YEARS)
    assert out["VE"]["likely"] is not None
