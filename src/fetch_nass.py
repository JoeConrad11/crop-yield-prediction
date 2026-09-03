"""Pull county-level crop yield data from USDA NASS QuickStats API."""
import os
import requests
import pandas as pd
from dotenv import load_dotenv

from config import STATE_ALPHAS, YEAR_START, YEAR_END, CROPS

load_dotenv()

API_URL = "https://quickstats.nass.usda.gov/api/api_GET/"
API_KEY = os.environ["NASS_API_KEY"]


def fetch_county_yield(commodity: str, state_alpha: str, year_start: int, year_end: int) -> pd.DataFrame:
    """Fetch annual county-level yield (units/acre) for a commodity and state."""
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
    resp.raise_for_status()
    data = resp.json()["data"]
    df = pd.DataFrame(data)
    keep = [
        "year", "state_alpha", "county_name", "county_code",
        "commodity_desc", "short_desc", "Value", "unit_desc",
    ]
    df = df[[c for c in keep if c in df.columns]].copy()
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
        df = fetch_multi_state_yield(commodity=CROPS[crop]["nass_commodity"], state_alphas=STATE_ALPHAS,
                                      year_start=YEAR_START, year_end=YEAR_END)
        out_path = f"data/raw/nass_{crop}_yield_multistate.csv"
        df.to_csv(out_path, index=False)
        print(f"Saved {len(df)} rows to {out_path}\n")
