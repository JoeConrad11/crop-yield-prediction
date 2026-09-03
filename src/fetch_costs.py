"""Pull USDA ERS Commodity Costs and Returns data (per-acre production costs
by crop and farm-resource region) -- fills the "gross revenue vs. profit"
gap in compare_crops.py. No API; ERS publishes these as static CSV files
that update a few times a year.

https://www.ers.usda.gov/data-products/commodity-costs-and-returns

IMPORTANT: ERS's cost estimate for a given year is calibrated against ERS's
OWN price/yield assumptions for that same year. compare_crops.py combines
this (necessarily stale -- there's no newer cost data to use) cost estimate
with a LIVE current price, which can diverge a lot from what ERS assumed
(soybean price moved ~15-18% between the 2025 ERS baseline and mid-2026
live prices in one check). That mismatch can materially swing which crop
looks more profitable. The fix isn't eliminating the mismatch -- there's no
more current cost data available -- it's making it visible: this module
also exposes ERS's own self-consistent net-value line (their price x their
yield - their cost) as a baseline to compare our live-price estimate against.
"""
import requests
import pandas as pd

from config import CROPS, STATE_TO_ERS_REGION

ERS_CSV_URLS = {
    "corn": "https://www.ers.usda.gov/media/4962/corn.csv",
    "soybeans": "https://www.ers.usda.gov/media/4976/soybeans.csv",
    "wheat": "https://www.ers.usda.gov/media/4978/wheat.csv",
}

TOTAL_COST_ITEM = "Total, costs listed"
NET_VALUE_ITEM = "Value of production less total costs listed"
PRICE_ITEM = "Price"

_cache = {}


def fetch_crop_costs(crop: str) -> pd.DataFrame:
    if crop not in _cache:
        resp = requests.get(ERS_CSV_URLS[crop], timeout=60)
        resp.raise_for_status()
        with open(f"data/raw/ers_costs_{crop}.csv", "wb") as f:
            f.write(resp.content)
        _cache[crop] = pd.read_csv(f"data/raw/ers_costs_{crop}.csv")
    return _cache[crop]


def _region_rows(crop: str, state_alpha: str, item: str) -> pd.DataFrame:
    region = STATE_TO_ERS_REGION[state_alpha]
    df = fetch_crop_costs(crop)
    rows = df[(df["Item"] == item) & (df["Region"] == region)]
    if rows.empty:
        rows = df[(df["Item"] == item) & (df["Region"] == "U.S. total")]  # fallback
    return rows


def latest_cost_per_acre(crop: str, state_alpha: str) -> float:
    rows = _region_rows(crop, state_alpha, TOTAL_COST_ITEM)
    latest_year = rows["Year"].max()
    return rows[rows["Year"] == latest_year]["Value"].iloc[0]


def cost_basis_year(crop: str, state_alpha: str) -> int:
    rows = _region_rows(crop, state_alpha, TOTAL_COST_ITEM)
    return int(rows["Year"].max())


def ers_baseline_net_value(crop: str, state_alpha: str) -> float:
    """ERS's own self-consistent net value (their price x their yield -
    their cost) for the same basis year as latest_cost_per_acre -- a
    reference point that isn't affected by our live-price/stale-cost mismatch."""
    rows = _region_rows(crop, state_alpha, NET_VALUE_ITEM)
    latest_year = rows["Year"].max()
    return rows[rows["Year"] == latest_year]["Value"].iloc[0]


def ers_baseline_price(crop: str, state_alpha: str) -> float:
    rows = _region_rows(crop, state_alpha, PRICE_ITEM)
    latest_year = rows["Year"].max()
    return rows[rows["Year"] == latest_year]["Value"].iloc[0]


if __name__ == "__main__":
    rows = []
    for crop in CROPS:
        for state in STATE_TO_ERS_REGION:
            cost = latest_cost_per_acre(crop, state)
            net = ers_baseline_net_value(crop, state)
            year = cost_basis_year(crop, state)
            rows.append({"crop": crop, "state_alpha": state, "region": STATE_TO_ERS_REGION[state],
                         "basis_year": year, "cost_per_acre": cost, "ers_baseline_net_value": net})
            print(f"{crop} / {state} ({STATE_TO_ERS_REGION[state]}, {year}): "
                  f"cost ${cost:.2f}/acre, ERS's own net value ${net:.2f}/acre")
    pd.DataFrame(rows).to_csv("data/raw/latest_costs.csv", index=False)
    print("Saved data/raw/latest_costs.csv")
