"""Compare predicted corn vs. soybean outcomes per county and surface a
data-driven signal on which crop looks more profitable this season.

IMPORTANT LIMITATIONS (surfaced in the output, not just this docstring):
1. Costs are region-level (USDA ERS farm-resource regions), not county- or
   farm-specific -- an individual farm's actual input costs will differ.
   Nebraska in particular straddles two ERS regions (Heartland east,
   Northern Great Plains west) and is approximated here as entirely
   Northern Great Plains, which understates costs for eastern-NE counties.
2. Crop-rotation is now a real model input (see fetch_rotation.py --
   pct_continuous, an empirical CDL-derived signal), not ignored, but its
   effect on predicted yield is modest (~7 bu/acre for a highly-continuous
   county in one check) compared to the price/cost effects below -- don't
   expect it to be the dominant factor in which crop wins here.
3. Price/cost basis-year mismatch is now CORRECTED, not just flagged: ERS's
   stale cost estimate is escalated using NASS's "PRODUCTION ITEMS - INDEX
   FOR PRICE PAID" (see fetch_price_paid_index.py) to a current-period
   equivalent before comparing against the live output price. The
   transparency columns (raw ERS cost, escalation ratio, ERS's own baseline
   net value) are kept as a secondary sanity check on that correction, not
   the primary number.
4. Price is the latest available MONTHLY STATE price received, not a live
   spot/futures price and not county-specific -- a reasonable proxy, not a
   precise number to trade on.
"""
import pandas as pd

from config import CROPS, STATES, STATE_TO_ERS_REGION, crop_state_alphas
from predict_live import predict, completed_periods, pick_checkpoint, \
    fetch_current_weather_and_moisture, latest_available_cdl_year, CHECKPOINTS
from fetch_prices import latest_price
from fetch_costs import latest_cost_per_acre, ers_baseline_net_value, ers_baseline_price, cost_basis_year
from fetch_price_paid_index import escalation_ratio
from datetime import date

CAVEATS = (
    "LIMITATIONS: (1) costs are region-level (USDA ERS farm-resource regions), not "
    "farm-specific -- NE is approximated as entirely Northern Great Plains though it "
    "spans two ERS regions; (2) crop-rotation is now a real model input (pct_continuous, "
    "empirical from CDL year-over-year) but its effect is modest (~7 bu/acre in one check) "
    "next to price/cost effects; (3) the price/cost basis-year mismatch is now CORRECTED "
    "(ERS cost escalated by the NASS Prices Paid Index ratio to a current-period "
    "equivalent), not just flagged -- see 'cost_escalation_ratio' and the raw "
    "'ers_basis_cost_per_acre' columns for the correction applied, and "
    "'ers_baseline_net_value' for ERS's own internally-consistent net value as a "
    "secondary sanity check."
)


def build_comparison(as_of: date = None, predictions: dict = None) -> pd.DataFrame:
    """predictions lets a caller (e.g. run_pipeline.py) pass in results it
    already fetched, instead of this function re-fetching from GEE."""
    as_of = as_of or date.today()

    if predictions is None:
        done = completed_periods(as_of)
        checkpoint_name = pick_checkpoint(done)
        periods = CHECKPOINTS[checkpoint_name] if checkpoint_name else []
        weather_moisture_cache = fetch_current_weather_and_moisture(as_of.year, periods) if periods else None
        cdl_year = latest_available_cdl_year()
        predictions = {crop: predict(crop, as_of, weather_moisture_cache, cdl_year) for crop in CROPS}

    # Long/tidy: one row per (crop, county), not one row per county with
    # per-crop column pairs -- lets this scale past 2 crops with no code
    # change (see src/config.py CROPS).
    frames = []
    for crop in CROPS:
        df = predictions[crop][["year", "state_fips", "county_fips", "county_name", "predicted_yield_bu_acre"]] \
            .rename(columns={"predicted_yield_bu_acre": "yield_bu_acre"}).copy()
        df["crop"] = crop
        frames.append(df)
    merged = pd.concat(frames, ignore_index=True)

    state_map = {v: k for k, v in STATES.items()}
    merged["state_alpha"] = merged["state_fips"].astype(str).str.zfill(2).map(state_map)

    price_cache, cost_cache, ers_net_cache, ers_price_cache, basis_year_cache, escalation_cache = \
        {}, {}, {}, {}, {}, {}
    for crop in CROPS:
        for state_alpha in crop_state_alphas(crop):
            price_cache[(crop, state_alpha)] = latest_price(crop, state_alpha, as_of.year)
            cost_cache[(crop, state_alpha)] = latest_cost_per_acre(crop, state_alpha)
            ers_net_cache[(crop, state_alpha)] = ers_baseline_net_value(crop, state_alpha)
            ers_price_cache[(crop, state_alpha)] = ers_baseline_price(crop, state_alpha)
            basis_year = cost_basis_year(crop, state_alpha)
            basis_year_cache[(crop, state_alpha)] = basis_year
            escalation_cache[(crop, state_alpha)] = escalation_ratio(basis_year, as_of.year)

    key = list(zip(merged["crop"], merged["state_alpha"]))
    merged["price_per_bu"] = [price_cache[k] for k in key]
    merged["ers_basis_cost_per_acre"] = [cost_cache[k] for k in key]
    merged["cost_escalation_ratio"] = [escalation_cache[k] for k in key]
    # PRIMARY cost figure: ERS's stale basis-year cost, escalated to a
    # current-period equivalent via the NASS Prices Paid Index ratio --
    # this is the actual correction, not just a transparency column.
    merged["cost_per_acre"] = merged["ers_basis_cost_per_acre"] * merged["cost_escalation_ratio"]
    merged["revenue_per_acre"] = merged["yield_bu_acre"] * merged["price_per_bu"]
    merged["profit_per_acre"] = merged["revenue_per_acre"] - merged["cost_per_acre"]
    # secondary sanity-check columns: how much has live price diverged from
    # ERS's own basis-year price, and what ERS's own self-consistent net value was
    merged["cost_basis_year"] = [basis_year_cache[k] for k in key]
    merged["ers_basis_price_per_bu"] = [ers_price_cache[k] for k in key]
    merged["price_vs_ers_basis_pct"] = 100 * (
        merged["price_per_bu"] - merged["ers_basis_price_per_bu"]
    ) / merged["ers_basis_price_per_bu"]
    merged["ers_baseline_net_value"] = [ers_net_cache[k] for k in key]

    # "Which crop wins" is a read-time computation over however many crops
    # are present, not a persisted binary field -- see __main__ below and
    # api/routers/comparisons.py for where this gets computed for consumers.
    return merged.sort_values(["state_alpha", "county_fips", "crop"]).reset_index(drop=True)


if __name__ == "__main__":
    result = build_comparison()
    out_path = f"data/processed/crop_comparison_{date.today().isoformat()}.csv"
    result.to_csv(out_path, index=False)

    print(f"\nSaved {len(result)} county-crop rows to {out_path}\n")
    print(CAVEATS)
    print()

    print("=== Cost escalation applied (by state/crop) ===")
    esc_check = result.drop_duplicates(["state_alpha", "crop"])[
        ["state_alpha", "crop", "ers_basis_cost_per_acre", "cost_escalation_ratio", "cost_per_acre"]
    ]
    print(esc_check.to_string(index=False))
    print()

    print("=== Price basis-year mismatch, for reference (by state/crop) ===")
    price_check = result.drop_duplicates(["state_alpha", "crop"])[
        ["state_alpha", "crop", "price_per_bu", "ers_basis_price_per_bu", "price_vs_ers_basis_pct"]
    ]
    print(price_check.to_string(index=False))
    print()

    # "Best crop per county" computed ad hoc for this CLI summary, display
    # only -- generalizes to however many crops are in CROPS, unlike the old
    # persisted profit_edge_crop binary field.
    best_idx = result.groupby(["state_fips", "county_fips"])["profit_per_acre"].idxmax()
    best = result.loc[best_idx, ["county_name", "state_alpha", "crop", "profit_per_acre"]] \
        .rename(columns={"crop": "best_crop", "profit_per_acre": "best_profit_per_acre"})
    print(best.head(20).to_string(index=False))
    print(f"\nBest-crop counts: {best['best_crop'].value_counts().to_dict()}")

    print("\n=== Sanity check: ERS's own self-consistent net value (not live-price-based), by state/crop ===")
    ers_check = result.drop_duplicates(["state_alpha", "crop"])[
        ["state_alpha", "crop", "cost_basis_year", "ers_baseline_net_value"]
    ]
    print(ers_check.to_string(index=False))
    print("If this shows all crops negative/similar while the live comparison above shows a large gap, "
          "the gap is likely driven by the price/cost timing mismatch, not a real profitability difference.")
