"""Layer 3 (see ARCHITECTURE.md, "Layer 3 -- Advice, sourced not invented").

Every note below paraphrases a specific, checkable Iowa State University
Extension and Outreach publication -- never model-generated prose -- and
`matching_notes()` only returns one when the field's own computed stage AND
its own measured stress metrics actually match the condition it describes.
A note existing is not enough to show it: this project measures stress
(fetch_prism.fetch_period_stress) for exactly two (crop, checkpoint) pairs
(see build_dataset.NEEDS_STRESS -- decided by evaluate_stress_features.py's
leave-one-year-out gate, the same discipline this file follows), so sourced
notes are scoped to exactly those two. Everywhere else the honest answer is
no note, not a hedged one -- same principle as predict_field.py declining a
number it can't back with real coverage.

STRESS_ELEVATED thresholds:
- edd_29c > 0 is not a judgment call: Schlenker & Roberts (2009) define this
  metric as degree-days accumulated ABOVE 29C specifically because that is
  where their yield-response curve turns negative, so any accumulation here
  is, by the metric's own construction, in the damaging range.
- dry_days >= 15 (out of a ~30-day period) IS a judgment call, stated rather
  than hidden: "at least half the days in the period had under 1mm of rain."
  No field-level historical baseline is fetched live to compare against (that
  would need its own validation pass, same rigor as the coverage-tier and
  Sentinel-2 gates elsewhere in this project), so this is a plain, fixed
  reading of the metric itself, not a percentile against this field's norm.
"""

CORN_POLLINATION_STAGES = {"VT", "R1", "R2"}
SOY_POD_SEED_FILL_STAGES = {"R3", "R5", "R6"}

DRY_DAYS_THRESHOLD = 15

NOTES = [
    {
        "id": "corn_pollination_heat_drought",
        "crop": "corn",
        "stages": CORN_POLLINATION_STAGES,
        # corn/early_season is the only NEEDS_STRESS checkpoint for corn,
        # covering jun/jul -- see config.CHECKPOINTS.
        "periods": ("jun", "jul"),
        "source_name": "Iowa State University Extension and Outreach",
        "source_url": "https://crops.extension.iastate.edu/encyclopedia/corn-pollination-effect-high-temperature-and-stress",
        # The heat/drought pollination mechanics are on the page above; the
        # "up to nine percent per day" figure is only in this second ISU
        # article, so it is cited here rather than attributed to the first.
        "extra_sources": [{
            "source_name": "Iowa State University Extension and Outreach (2017 drought article)",
            "source_url": "https://crops.extension.iastate.edu/cropnews/2017/07/influence-drought-corn-and-soybean",
        }],
        "text": (
            "Pollination is corn's single most heat- and drought-sensitive window: "
            "temperatures in the mid-90s(F) and above kill pollen viability, and "
            "drought slows silk emergence while speeding pollen shed, so silks can "
            "miss the pollen window entirely. ISU field data puts severe combined "
            "heat/drought stress here at up to roughly 9% yield loss per day -- "
            "several times the daily cost of the same stress earlier or later in "
            "the season."
        ),
    },
    {
        "id": "soybean_pod_seed_fill_drought",
        "crop": "soybeans",
        "stages": SOY_POD_SEED_FILL_STAGES,
        # soybeans/pre_harvest is the only NEEDS_STRESS checkpoint for
        # soybeans, covering jun/jul/aug.
        "periods": ("jun", "jul", "aug"),
        "source_name": "Iowa State University Extension and Outreach",
        "source_url": "https://crops.extension.iastate.edu/cropnews/2017/07/influence-drought-corn-and-soybean",
        "text": (
            "Pod set through seed fill is soybean's peak water demand and its most "
            "drought-sensitive stretch. Prolonged dry weather here can abort "
            "flowers and pods -- up to roughly 20% fewer pods in ISU field data -- "
            "and the plant has much less room to compensate later than it does "
            "from stress earlier in the season."
        ),
    },
]


def _stress_elevated(row: dict, periods: tuple) -> bool:
    for period in periods:
        edd = row.get(f"edd_29c_{period}")
        if edd is not None and edd > 0:
            return True
        dry = row.get(f"dry_days_{period}")
        if dry is not None and dry >= DRY_DAYS_THRESHOLD:
            return True
    return False


def matching_notes(crop: str, stage_code: str, row: dict) -> list:
    """`row`: the field's fetched feature row (fetch_field_features.py's
    output) for the checkpoint currently active for this field/date, or None
    if it wasn't available (e.g. the yield path refused this field). Without
    a row there's nothing measured to condition on, so no notes fire --
    consistent with the rest of this project's refusal-over-guessing rule."""
    if not row:
        return []
    matches = []
    for note in NOTES:
        if note["crop"] != crop or stage_code not in note["stages"]:
            continue
        if not _stress_elevated(row, note["periods"]):
            continue
        matches.append({
            "id": note["id"],
            "source_name": note["source_name"],
            "source_url": note["source_url"],
            "extra_sources": note.get("extra_sources", []),
            "text": note["text"],
        })
    return matches
