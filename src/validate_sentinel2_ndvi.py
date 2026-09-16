"""Phase 4a validation (see ../ARCHITECTURE.md): before Sentinel-2 NDVI can
feed the live field-level prediction path, check how its values relate to
the MODIS NDVI the models were actually CALIBRATED on.

Why this exists: swapping the field-level NDVI source from MODIS
(250m/pixel) to Sentinel-2 (10m/pixel) is what makes small fields workable
at all -- a sub-40-acre field often has zero usable MODIS pixels. But
Sentinel-2 and MODIS are different sensors with different band responses,
different atmospheric correction, and different compositing (MODIS ships a
pre-cleaned 16-day composite; we build our own cloud-masked median from raw
S2 scenes). Feeding raw Sentinel-2 numbers into a MODIS-calibrated model
would stack a silent sensor bias on top of the already-declared
county-model/field-input approximation. Same "verify it by hand before
shipping it" rule that caught the reduceRegion band-prefix bug and the
ERA5 coarse-scale bug in Phase 2.

Method: both sources, same counties, same crop mask, same periods, same
years -> fit MODIS_ndvi ~ a * S2_ndvi + b, per period and pooled. MODIS
county values come from the historical pull already on disk
(data/raw/gee_ndvi_<crop>_periods.csv); only the Sentinel-2 side is
fetched here.

Scope: Iowa only by default, not all 4 states -- a full 4-state
reduceRegions call at this resolution runs past 2 minutes, while Iowa's 99
counties take ~1 minute per (year, period). 99 counties x 3 years x 3
periods is ~890 paired observations, plenty to fit a 2-parameter line and
see whether the relationship is stable across periods.

Sentinel-2 caveat on year choice: S2A launched mid-2015 and S2B in 2017,
so revisit frequency (and therefore how cloud-free a monthly median
composite can get) is materially worse before ~2018. Default sample years
are all well after that.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from config import CROPS, STATES, crop_periods
from fetch_gee import fetch_period_ndvi_s2

SAMPLE_STATES = ["19"]  # Iowa -- see module docstring on why not all 4

# Every year with a clean dual-satellite Sentinel-2 record. S2A launched
# mid-2015 and S2B in March 2017, so revisit frequency (and therefore how
# cloud-free a monthly median can get) is materially worse before 2018.
#
# Deliberately 8 years, not the 3 this started with: the yield-signal test
# compares ANOMALIES, and an anomaly is only as good as the county mean it
# is measured against. With 3 years that mean is estimated from 3 points and
# the resulting noise attenuates both sensors -- enough to make a ~0.07
# pooled gap between them uninterpretable. The production model estimates
# county means from ~15 years, so 8 is much closer to the regime the model
# actually operates in.
SAMPLE_YEARS = [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]
OUT_PATH = Path("models/s2_ndvi_correction.json")
SAMPLE_CSV = Path("data/processed/s2_vs_modis_ndvi_sample.csv")


def fetch_s2_sample(crop: str, states: list, years: list) -> pd.DataFrame:
    """Sentinel-2 county NDVI for every (year, period) in the sample. One
    reduceRegions call per (year, period) -- each takes roughly a minute
    for Iowa, so this is a slow one-off, not something to run casually."""
    cdl_code = CROPS[crop]["cdl_code"]
    frames = []
    for period_name, (start_md, end_md) in crop_periods(crop).items():
        for year in years:
            print(f"[{crop}] Sentinel-2 {period_name} {year}...")
            frames.append(fetch_period_ndvi_s2(states, year, year, period_name,
                                                start_md, end_md, cdl_code))
    return pd.concat(frames, ignore_index=True)


def load_modis_sample(crop: str, states: list, years: list) -> pd.DataFrame:
    """MODIS side comes off disk -- already fetched by fetch_gee.py's
    historical run, no reason to re-pull it."""
    df = pd.read_csv(f"data/raw/gee_ndvi_{crop}_periods.csv")
    df["state_fips"] = df["state_fips"].astype(str).str.zfill(2)
    df["county_fips"] = df["county_fips"].astype(str).str.zfill(3)
    return df[df["state_fips"].isin(states) & df["year"].isin(years)].rename(
        columns={"ndvi_mean": "ndvi_mean_modis", "crop_pixel_count": "crop_pixel_count_modis"}
    )


def fit_correction(paired: pd.DataFrame) -> dict:
    """MODIS_ndvi ~ slope * S2_ndvi + intercept. Reported per period as well
    as pooled: if the per-period slopes are wildly different, one global
    correction is the wrong shape and this needs a per-period (or
    growth-stage-aware) correction instead."""
    def _fit(df: pd.DataFrame) -> dict:
        x = df["ndvi_mean_s2"].to_numpy()
        y = df["ndvi_mean_modis"].to_numpy()
        slope, intercept = np.polyfit(x, y, 1)
        predicted = slope * x + intercept
        ss_res = float(np.sum((y - predicted) ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        return {
            "slope": float(slope),
            "intercept": float(intercept),
            "r2": 1 - ss_res / ss_tot if ss_tot else float("nan"),
            "rmse": float(np.sqrt(np.mean((y - predicted) ** 2))),
            "mean_abs_gap_uncorrected": float(np.mean(np.abs(y - x))),
            "mean_abs_gap_corrected": float(np.mean(np.abs(y - predicted))),
            "n": int(len(df)),
        }

    return {
        "pooled": _fit(paired),
        "by_period": {period: _fit(group) for period, group in paired.groupby("period")},
    }


def yield_signal_test(paired: pd.DataFrame, crop: str) -> dict:
    """THE decision gate for Sentinel-2, and the one test that isn't
    circular: does each sensor's NDVI anomaly actually track real county
    YIELD (USDA NASS, the only ground truth this project has)?

    Correlating the two sensors against each other only says whether they
    agree, not which one is right -- and they measurably disagree. Sentinel-2
    carries ~3x MODIS's anomaly spread, which is either real signal MODIS
    smooths away or contamination; only yield distinguishes those. Compared
    on ANOMALIES (county value minus that county's own mean), because that
    is what the model actually consumes -- feature-importance analysis shows
    anom_ndvi_jul is the single most important feature in every corn/soybean
    model (0.28-0.38), while the raw ndvi_* levels rank near the bottom."""
    y = pd.read_csv(f"data/processed/model_table_{crop}_pre_harvest.csv")
    y["state_fips"] = y["state_fips"].astype(str).str.zfill(2)
    y["county_fips"] = y["county_fips"].astype(str).str.zfill(3)
    d = paired.merge(y[["year", "state_fips", "county_fips", "yield_bu_acre"]],
                      on=["year", "state_fips", "county_fips"], how="inner")
    if d.empty:
        return {"error": "no yield rows matched the sample"}

    group = ["state_fips", "county_fips", "period"]
    for col in ["ndvi_mean_modis", "ndvi_mean_s2", "yield_bu_acre"]:
        d["a_" + col] = d[col] - d.groupby(group)[col].transform("mean")

    def _r(a, b):
        return float(np.corrcoef(a, b)[0, 1])

    result = {"n": int(len(d)), "by_period": {}}
    for period, dd in d.groupby("period"):
        result["by_period"][period] = {
            "modis_vs_yield": _r(dd["a_ndvi_mean_modis"], dd["a_yield_bu_acre"]),
            "s2_vs_yield": _r(dd["a_ndvi_mean_s2"], dd["a_yield_bu_acre"]),
            "n": int(len(dd)),
        }
    result["pooled"] = {
        "modis_vs_yield": _r(d["a_ndvi_mean_modis"], d["a_yield_bu_acre"]),
        "s2_vs_yield": _r(d["a_ndvi_mean_s2"], d["a_yield_bu_acre"]),
    }
    return result


def main(crop: str = "corn"):
    s2 = fetch_s2_sample(crop, SAMPLE_STATES, SAMPLE_YEARS)
    modis = load_modis_sample(crop, SAMPLE_STATES, SAMPLE_YEARS)

    s2["state_fips"] = s2["state_fips"].astype(str).str.zfill(2)
    s2["county_fips"] = s2["county_fips"].astype(str).str.zfill(3)

    keys = ["year", "period", "state_fips", "county_fips"]
    paired = s2.merge(modis[keys + ["ndvi_mean_modis", "crop_pixel_count_modis"]], on=keys, how="inner")
    paired = paired.dropna(subset=["ndvi_mean_s2", "ndvi_mean_modis"])
    print(f"\nPaired observations: {len(paired)}")

    correction = fit_correction(paired)
    correction["crop"] = crop
    correction["sample_states"] = [a for a, f in STATES.items() if f in SAMPLE_STATES]
    correction["sample_years"] = SAMPLE_YEARS

    SAMPLE_CSV.parent.mkdir(parents=True, exist_ok=True)
    paired.to_csv(SAMPLE_CSV, index=False)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(correction, indent=2))

    pooled = correction["pooled"]
    print(f"\nPooled fit: MODIS = {pooled['slope']:.4f} * S2 + {pooled['intercept']:.4f}")
    print(f"  r2={pooled['r2']:.3f}  rmse={pooled['rmse']:.4f}  n={pooled['n']}")
    print(f"  mean |MODIS - S2| raw:       {pooled['mean_abs_gap_uncorrected']:.4f}")
    print(f"  mean |MODIS - corrected S2|: {pooled['mean_abs_gap_corrected']:.4f}")
    print("\nPer period:")
    for period, fit in correction["by_period"].items():
        print(f"  {period}: slope={fit['slope']:.4f} intercept={fit['intercept']:.4f} "
              f"r2={fit['r2']:.3f} n={fit['n']}")

    # The decision gate -- see yield_signal_test's docstring.
    signal = yield_signal_test(paired, crop)
    correction["yield_signal_test"] = signal
    OUT_PATH.write_text(json.dumps(correction, indent=2))

    print("\n=== YIELD SIGNAL TEST (decides whether S2 is usable at all) ===")
    if "error" in signal:
        print(f"  {signal['error']}")
    else:
        print(f"  {'period':8} {'MODIS vs yield':>15} {'S2 vs yield':>13} {'winner':>8}")
        for period, r in signal["by_period"].items():
            win = "MODIS" if r["modis_vs_yield"] > r["s2_vs_yield"] else "S2"
            print(f"  {period:8} {r['modis_vs_yield']:15.3f} {r['s2_vs_yield']:13.3f} {win:>8}")
        p = signal["pooled"]
        win = "MODIS" if p["modis_vs_yield"] > p["s2_vs_yield"] else "S2"
        print(f"  {'POOLED':8} {p['modis_vs_yield']:15.3f} {p['s2_vs_yield']:13.3f} {win:>8}")

    print(f"\nSaved {OUT_PATH} and {SAMPLE_CSV}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "corn")
