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

# Winter wheat's real season doesn't match corn/soybean's summer PERIODS
# above -- it's fall-planted, overwinters, and is typically harvested by
# early-mid summer in these states (NC ~mid-June, IL ~late June/early July,
# NE ~July). By the time PERIODS' "aug" period completes, wheat has already
# been harvested -- the model would be reading bare/stubble ground, not a
# growing crop. Use wheat's actual spring growth window (green-up through
# just before the earliest state's harvest) instead, so "pre_harvest" means
# the same thing for wheat that it means for corn/soybean: the last
# checkpoint before harvest starts. Same fixed-calendar-across-states
# simplification as PERIODS above (a state-specific offset, e.g. for NC's
# earlier harvest, is a further follow-up, not done here).
WHEAT_PERIODS = {
    "mar": ("03-01", "03-31"),
    "apr": ("04-01", "04-30"),
    "may": ("05-01", "05-31"),
}
WHEAT_CHECKPOINTS = {
    "early_season": ["mar", "apr"],
    "pre_harvest": ["mar", "apr", "may"],
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
    # Winter wheat specifically (yield_label/price_label both hand-verified
    # against the live NASS API, cdl_code=24 verified against GEE's own CDL
    # legend -- NASS also separately tracks Spring/Durum wheat, not what's
    # grown in these states). No county-level NASS yield data exists for
    # Iowa at all (0 counties, all years checked) -- wheat will only ever
    # cover IL/NE/NC, not all 4 states, and that's a real data gap, not a
    # bug. Also: winter wheat's actual season (fall-planted, harvested by
    # early summer) doesn't line up with the Jun/Jul/Aug PERIODS/CHECKPOINTS
    # below, which were built around corn/soybean's summer season -- by the
    # "pre_harvest" checkpoint, wheat is likely already harvested in
    # reality. Same category of known simplification as the NC calendar
    # note above; a wheat-specific season calendar is a candidate follow-up,
    # not done here.
    "wheat": {
        "display_name": "Wheat",
        "nass_commodity": "WHEAT",
        "yield_label": "WHEAT, WINTER - YIELD, MEASURED IN BU / ACRE",
        "price_label": "WHEAT, WINTER - PRICE RECEIVED, MEASURED IN $ / BU",
        "cdl_code": 24,
        # Explicit subset -- see the comment above. Iowa is deliberately
        # excluded, not just "happens to have no rows": without this, the
        # live pipeline would still generate NDVI features for IA counties
        # (CDL crop-masking doesn't care whether NASS publishes yield for a
        # state) and run them through a model that never saw a single real
        # IA wheat yield during training -- an untested extrapolation the
        # confidence-tier system has no way to flag, so it's excluded
        # upstream instead.
        "states": ["IL", "NE", "NC"],
        "periods": WHEAT_PERIODS,
        "checkpoints": WHEAT_CHECKPOINTS,
    },
}


def crop_state_alphas(crop: str) -> list:
    """State alpha codes this crop actually has data for -- STATE_ALPHAS
    (all 4) unless the crop's CROPS entry narrows it (see "wheat" above)."""
    return CROPS[crop].get("states", STATE_ALPHAS)


def crop_state_fips(crop: str) -> list:
    """FIPS codes for the states this crop actually has data for."""
    return [STATES[a] for a in crop_state_alphas(crop)]


def crop_periods(crop: str) -> dict:
    """This crop's growing-season monthly periods -- PERIODS (summer)
    unless the crop's CROPS entry overrides it (wheat's spring calendar,
    see WHEAT_PERIODS above)."""
    return CROPS[crop].get("periods", PERIODS)


def crop_checkpoints(crop: str) -> dict:
    """This crop's season checkpoints -- CHECKPOINTS unless overridden (see crop_periods)."""
    return CROPS[crop].get("checkpoints", CHECKPOINTS)


def all_periods() -> dict:
    """Union of every crop's periods, keyed by period name. Period names are
    unique across crops (wheat's mar/apr/may vs. corn/soybean's jun/jul/aug
    don't collide), so this merge is safe. Used by the crop-agnostic
    weather/soil-moisture fetches, which need to cover whichever periods ANY
    crop's calendar requires, not just one crop's."""
    merged = {}
    for crop in CROPS:
        merged.update(crop_periods(crop))
    return merged
