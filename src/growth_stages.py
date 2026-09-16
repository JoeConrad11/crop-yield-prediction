"""Agronomy Layer 1 (see ../ARCHITECTURE.md, "Bringing real agronomy in"):
turn accumulated heat into a crop growth stage.

Why this exists: the pipeline slices the season into fixed calendar months
(jun/jul/aug), but crops develop on accumulated heat, not on the calendar.
Two fields planted three weeks apart are at genuinely different stages on
the same July date, and yield sensitivity is strongly stage-dependent --
moisture and heat stress during corn pollination is one of the
best-established yield determinants in agronomy, while identical stress two
weeks earlier costs far less. Calendar months smear that distinction.

This module is deliberately just the domain knowledge (thresholds and what
they mean). The heat accumulation itself is fetch_prism.fetch_field_gdd().

SOURCING: the corn thresholds below are the standard GDU values published
by Midwest land-grant extension services (Iowa State / Purdue corn growth
and development guides) for the ~105-115 day hybrids common in this
project's states. They are approximations, and the caveats in
CROP_STAGE_MODELS are part of the data, not decoration -- per
ARCHITECTURE.md's rule that agronomic claims are sourced, never invented.
"""

# Fahrenheit, the convention these thresholds are published in. GDU =
# (min(Tmax, cap) + max(Tmin, base)) / 2 - base, floored at zero, summed
# daily from planting.
CORN_BASE_F, CORN_CAP_F = 50.0, 86.0
SOY_BASE_F, SOY_CAP_F = 50.0, 86.0

# (cumulative GDU from planting, stage code, plain-language description)
CORN_STAGES = [
    (125, "VE", "emergence"),
    (345, "V4", "4 leaf collars"),
    (475, "V6", "6 leaf collars -- growing point above ground"),
    (740, "V10", "10 leaf collars -- rapid growth, high water demand"),
    (1250, "VT", "tasseling"),
    (1400, "R1", "silking -- pollination, the most yield-critical window"),
    (1660, "R2", "blister"),
    (1925, "R3", "milk"),
    (2190, "R4", "dough"),
    (2450, "R5", "dent -- grain fill finishing"),
    (2700, "R6", "physiological maturity (black layer)"),
]

# Soybean staging is only loosely thermal -- see the caveat below.
SOY_STAGES = [
    (90, "VE", "emergence"),
    (350, "V3", "3 trifoliates"),
    (700, "R1", "beginning bloom"),
    (900, "R3", "beginning pod"),
    (1200, "R5", "beginning seed -- grain fill, most yield-sensitive window"),
    (1700, "R6", "full seed"),
    (2100, "R7", "beginning maturity"),
    (2300, "R8", "full maturity"),
]

CROP_STAGE_MODELS = {
    "corn": {
        "stages": CORN_STAGES,
        "base_f": CORN_BASE_F,
        "cap_f": CORN_CAP_F,
        "confidence": "good",
        "caveat": "GDU-to-stage varies with hybrid maturity rating (roughly "
                   "2400-2900 GDU to black layer). These are typical values for "
                   "the 105-115 day hybrids common in this region, so treat a "
                   "stage as approximate unless you know your hybrid's rating.",
    },
    "soybeans": {
        "stages": SOY_STAGES,
        "base_f": SOY_BASE_F,
        "cap_f": SOY_CAP_F,
        "confidence": "approximate",
        "caveat": "Soybean development is driven substantially by DAY LENGTH, not "
                   "just heat, and varies by maturity group. Heat-based staging is "
                   "therefore materially less reliable for soybeans than for corn -- "
                   "treat these as rough orientation, not a scouting schedule.",
    },
    # Winter wheat is deliberately absent rather than guessed at. It is
    # fall-planted and overwinters, so "GDU accumulated since planting"
    # spans a dormant winter and does not describe development the way it
    # does for a spring-planted summer crop; proper winter wheat staging
    # needs vernalization and a different base temperature (typically 32F).
    # Inventing thresholds here would be exactly the fabricated-agronomy
    # failure ARCHITECTURE.md warns against.
}


def stage_model(crop: str) -> dict:
    """The staging model for a crop, or None where we don't have a defensible
    one (see the winter wheat note above)."""
    return CROP_STAGE_MODELS.get(crop)


def stage_for_gdd(crop: str, accumulated_gdd: float) -> dict:
    """Current stage, plus what's next and how much heat away it is.

    Returns None when the crop has no staging model, or when GDD is unknown.
    `next_stage_gdd_away` is what makes this actionable -- "pollination is
    ~180 GDU away, roughly 8 days at this time of year" is something a
    farmer can plan irrigation or scouting around, where a bare stage label
    is only a status."""
    model = stage_model(crop)
    if model is None or accumulated_gdd is None:
        return None

    stages = model["stages"]
    current = None
    upcoming = None
    for threshold, code, description in stages:
        if accumulated_gdd >= threshold:
            current = {"code": code, "description": description, "gdd_threshold": threshold}
        elif upcoming is None:
            upcoming = {"code": code, "description": description, "gdd_threshold": threshold}

    return {
        "accumulated_gdd": accumulated_gdd,
        "stage": current,  # None before emergence
        "next_stage": upcoming,  # None past the last modelled stage
        "next_stage_gdd_away": (upcoming["gdd_threshold"] - accumulated_gdd) if upcoming else None,
        "confidence": model["confidence"],
        "caveat": model["caveat"],
    }
