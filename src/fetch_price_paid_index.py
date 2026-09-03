"""USDA NASS "PRODUCTION ITEMS - INDEX FOR PRICE PAID" -- a national farm
input-cost index, updated monthly. Lets compare_crops.py escalate USDA ERS's
stale cost-basis-year estimate to a current-period-equivalent, instead of
just flagging the price/cost timing mismatch (see fetch_costs.py).
"""
import os
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://quickstats.nass.usda.gov/api/api_GET/"
API_KEY = os.environ["NASS_API_KEY"]
SERIES = "PRODUCTION ITEMS - INDEX FOR PRICE PAID, 2011"

_cache = None


def fetch_index() -> pd.DataFrame:
    global _cache
    if _cache is None:
        resp = requests.get(API_URL, params={
            "key": API_KEY, "sector_desc": "ECONOMICS", "group_desc": "PRICES PAID",
            "short_desc": SERIES, "agg_level_desc": "NATIONAL", "format": "JSON",
        }, timeout=30)
        resp.raise_for_status()
        df = pd.DataFrame(resp.json()["data"])
        df["Value"] = pd.to_numeric(df["Value"], errors="coerce")
        _cache = df
    return _cache


def annual_index(year: int) -> float:
    """ERS's cost basis year uses an annual estimate -- match that with the
    index's own "YEAR" (annual average) value for an apples-to-apples ratio."""
    df = fetch_index()
    row = df[(df["year"] == year) & (df["reference_period_desc"] == "YEAR")]
    return row["Value"].iloc[0]


def latest_index(year: int) -> float:
    """Most recent monthly value available for the given year -- falls back
    to the prior year's annual value if nothing's been reported yet."""
    df = fetch_index()
    monthly = df[(df["year"] == year) & (df["reference_period_desc"] != "YEAR")]
    if monthly.empty:
        return annual_index(year - 1)
    month_order = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    monthly = monthly.copy()
    monthly["month_rank"] = monthly["reference_period_desc"].map(month_order.index)
    return monthly.sort_values("month_rank").iloc[-1]["Value"]


def escalation_ratio(basis_year: int, current_year: int) -> float:
    """(current input-cost level) / (ERS's basis-year input-cost level)."""
    return latest_index(current_year) / annual_index(basis_year)


if __name__ == "__main__":
    from datetime import date
    current_year = date.today().year
    for basis_year in [2024, 2025]:
        ratio = escalation_ratio(basis_year, current_year)
        print(f"Basis year {basis_year} -> {current_year}: escalation ratio {ratio:.4f} "
              f"({(ratio - 1) * 100:+.1f}%)")
