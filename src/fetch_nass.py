"""Pull county-level crop yield data from USDA NASS QuickStats API."""
import os
import requests
import pandas as pd
from dotenv import load_dotenv

from config import YEAR_START, YEAR_END, CROPS, crop_state_alphas

load_dotenv()

API_URL = "https://quickstats.nass.usda.gov/api/api_GET/"
API_KEY = os.environ["NASS_API_KEY"]


KEEP_COLS = [
    "year", "state_alpha", "county_name", "county_code",
    "commodity_desc", "short_desc", "Value", "unit_desc",
]


def fetch_county_yield(commodity: str, state_alpha: str, year_start: int, year_end: int) -> pd.DataFrame:
    """Fetch annual county-level yield (units/acre) for a commodity and state.

    Not every crop is grown enough in every state to have county-level NASS
    survey data at all (e.g. wheat has zero rows for Iowa, every year
    checked) -- NASS's API returns a 400 "bad request - invalid query" for
    a genuinely empty result set, not a 200 with an empty list, so that
    specific case is treated as "no data" and returns an empty frame rather
    than crashing. Any other HTTP error still raises.
    """
    params = {
        "key": API_KEY,
        "commodity_desc": commodity.upper(),
        "state_alpha": state_alpha.upper(),
        "agg_level_desc": "COUNTY",
        "statisticcat_desc": "YIELD",
        "year__GE": year_start,
        "year__LE": year_end,
        "format": "JSON",
    }
    resp = requests.get(API_URL, params=params, timeout=60)
    if resp.status_code == 400:
        print(f"    (no NASS county-yield data for {commodity} in {state_alpha} -- treating as empty)")
        return pd.DataFrame(columns=KEEP_COLS)
    resp.raise_for_status()
    data = resp.json()["data"]
    df = pd.DataFrame(data)
    df = df[[c for c in KEEP_COLS if c in df.columns]].copy()
    df["Value"] = pd.to_numeric(df["Value"].str.replace(",", ""), errors="coerce")
    return df.sort_values(["county_name", "year"]).reset_index(drop=True)


def fetch_multi_state_yield(commodity: str, state_alphas: list, year_start: int, year_end: int) -> pd.DataFrame:
    frames = []
    for state in state_alphas:
        df = fetch_county_yield(commodity, state, year_start, year_end)
        frames.append(df)
        print(f"  fetched {state}: {len(df)} rows")
    return pd.concat(frames, ignore_index=True)


if __name__ == "__main__":
    import sys
    crops = sys.argv[1:] or list(CROPS.keys())
    for crop in crops:
        print(f"Crop: {crop}")
        df = fetch_multi_state_yield(commodity=CROPS[crop]["nass_commodity"], state_alphas=crop_state_alphas(crop),
                                      year_start=YEAR_START, year_end=YEAR_END)
        out_path = f"data/raw/nass_{crop}_yield_multistate.csv"
        df.to_csv(out_path, index=False)
        print(f"Saved {len(df)} rows to {out_path}\n")
