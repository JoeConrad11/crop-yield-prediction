"""Shared project configuration: states, years, monthly feature periods, and
season checkpoints."""

# Curated multi-state set: Corn Belt core (IA, IL, NE) + NC for cross-region signal
STATES = {
    "IA": "19",
    "IL": "17",
    "NE": "31",
    "NC": "37",
}
STATE_ALPHAS = list(STATES.keys())
STATE_FIPS = list(STATES.values())

# USDA ERS Commodity Costs and Returns are published by "farm resource region",
# not by state. Most of our states map cleanly to one region; Nebraska is the
# exception -- it straddles Heartland (east) and Northern Great Plains (west,
# the Panhandle), and our county set includes both. Northern Great Plains is
# used as the single approximation for NE, which understates costs for the
# eastern-NE counties in our data -- a known simplification, same spirit as
# the NC season-calendar approximation.
STATE_TO_ERS_REGION = {
    "IA": "Heartland",
    "IL": "Heartland",
    "NE": "Northern Great Plains",
    "NC": "Southern Seaboard",
}

YEAR_START = 2010
YEAR_END = 2025

# Monthly feature periods within the growing season. Each period gets its own
# NDVI + weather features (instead of one flat season-long average), so the
# model can see the trajectory across the season, not just a single mean.
# NOTE: NC's growing season runs ~3-4 weeks ahead of IA/IL/NE (earlier planting
# and harvest). Fixed calendar months are a simplification shared across all
# states for this pass -- a state-specific offset is a known follow-up if NC
# ends up behaving very differently in the results.
PERIODS = {
    "jun": ("06-01", "06-30"),
    "jul": ("07-01", "07-31"),
    "aug": ("08-01", "08-31"),
}

# Season checkpoints for in-season vs. pre-harvest forecasting, expressed as
# which periods' features are visible to the model at that checkpoint.
CHECKPOINTS = {
    "early_season": ["jun", "jul"],   # forecast made before August, no late-season data
    "pre_harvest": ["jun", "jul", "aug"],  # full season, all periods visible
}

# Crops supported by the pipeline. `cdl_code` is the USDA Cropland Data Layer
# value used to mask NDVI to that crop's pixels; `yield_label` is the exact
# NASS QuickStats short_desc string for county-level grain yield (verified
# against the live API -- corn has a grain/silage split with the same
# commodity_desc, soybeans doesn't, so this can't be derived generically).
CROPS = {
    "corn": {
        "display_name": "Corn",
        "nass_commodity": "CORN",
        "yield_label": "CORN, GRAIN - YIELD, MEASURED IN BU / ACRE",
        "price_label": "CORN, GRAIN - PRICE RECEIVED, MEASURED IN $ / BU",
        "cdl_code": 1,
    },
    "soybeans": {
        "display_name": "Soybeans",
        "nass_commodity": "SOYBEANS",
        "yield_label": "SOYBEANS - YIELD, MEASURED IN BU / ACRE",
        "price_label": "SOYBEANS - PRICE RECEIVED, MEASURED IN $ / BU",
        "cdl_code": 5,
    },
}
