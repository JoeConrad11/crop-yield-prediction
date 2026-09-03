"""Pull state-level monthly commodity prices from USDA NASS QuickStats.

Prices are a market-level statistic (not something that varies by county),
so this is state-level, unlike the county-level yield/NDVI/weather data.
Used to convert predicted yield (bu/acre) into predicted revenue ($/acre)
so corn and soybean predictions become comparable.
"""
import os
import requests
import pandas as pd
from dotenv import load_dotenv

from config import STATE_ALPHAS, CROPS

load_dotenv()

API_URL = "https://quickstats.nass.usda.gov/api/api_GET/"
API_KEY = os.environ["NASS_API_KEY"]


def fetch_state_prices(crop: str, state_alpha: str, year: int) -> pd.DataFrame:
    params = {
        "key": API_KEY,
        "commodity_desc": CROPS[crop]["nass_commodity"],
        "state_alpha": state_alpha,
        "statisticcat_desc": "PRICE RECEIVED",
        "agg_level_desc": "STATE",
        "year": year,
        "format": "JSON",
    }
    resp = requests.get(API_URL, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json().get("data", [])
    df = pd.DataFrame(data)
    if df.empty:
        return df
    df = df[df["short_desc"] == CROPS[crop]["price_label"]].copy()
    df["Value"] = pd.to_numeric(df["Value"], errors="coerce")
    return df[["year", "state_alpha", "reference_period_desc", "Value"]]


def latest_price(crop: str, state_alpha: str, year: int) -> float:
    """Most recent monthly price available for this crop/state/year -- falls
    back to the prior year if nothing's been reported yet this year."""
    df = fetch_state_prices(crop, state_alpha, year)
    if df.empty:
        df = fetch_state_prices(crop, state_alpha, year - 1)
    monthly = df[df["reference_period_desc"] != "MARKETING YEAR"]
    if monthly.empty:
        return df["Value"].iloc[-1] if not df.empty else None
    return monthly.sort_values("year").iloc[-1]["Value"]


if __name__ == "__main__":
    from datetime import date
    rows = []
    for crop in CROPS:
        for state in STATE_ALPHAS:
            price = latest_price(crop, state, date.today().year)
            rows.append({"crop": crop, "state_alpha": state, "price_per_bu": price})
            print(f"{crop} / {state}: ${price}/bu")
    pd.DataFrame(rows).to_csv("data/raw/latest_prices.csv", index=False)
    print("Saved data/raw/latest_prices.csv")
