"""matching_notes() must fire only for the right crop + stage + elevated
measured stress, and stay silent otherwise (see src/advice_sources.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from advice_sources import DRY_DAYS_THRESHOLD, matching_notes

CORN_ID = "corn_pollination_heat_drought"
SOY_ID = "soybean_pod_seed_fill_drought"


def ids(notes):
    return [n["id"] for n in notes]


def test_corn_fires_on_heat_stress_at_pollination():
    assert ids(matching_notes("corn", "R1", {"edd_29c_jul": 12.0})) == [CORN_ID]


def test_corn_fires_on_dry_days_at_threshold():
    row = {"dry_days_jun": DRY_DAYS_THRESHOLD}
    assert ids(matching_notes("corn", "VT", row)) == [CORN_ID]


def test_corn_silent_just_below_dry_threshold():
    row = {"dry_days_jun": DRY_DAYS_THRESHOLD - 1, "edd_29c_jun": 0}
    assert matching_notes("corn", "R1", row) == []


def test_corn_silent_outside_pollination_stages():
    assert matching_notes("corn", "V6", {"edd_29c_jul": 50.0}) == []
    assert matching_notes("corn", "R5", {"edd_29c_jul": 50.0}) == []


def test_soybean_fires_at_seed_fill_with_dry_weather():
    row = {"dry_days_aug": 20}
    assert ids(matching_notes("soybeans", "R5", row)) == [SOY_ID]


def test_soybean_silent_at_maturity():
    # R8 is past seed fill -- the field in the live preview screenshot.
    assert matching_notes("soybeans", "R8", {"dry_days_aug": 25}) == []


def test_wrong_crop_never_matches():
    assert matching_notes("wheat", "R1", {"edd_29c_jul": 50.0}) == []
    assert matching_notes("soybeans", "R1", {"edd_29c_jul": 50.0}) == []


def test_no_row_means_no_notes():
    assert matching_notes("corn", "R1", None) == []
    assert matching_notes("corn", "R1", {}) == []


def test_missing_metrics_are_not_treated_as_stress():
    assert matching_notes("corn", "R1", {"edd_29c_jul": None, "dry_days_jul": None}) == []


def test_stress_in_unrelated_period_is_ignored():
    # corn note only looks at jun/jul; aug stress must not fire it
    assert matching_notes("corn", "R1", {"edd_29c_aug": 40.0}) == []


def test_note_carries_source_citation():
    note = matching_notes("corn", "R1", {"edd_29c_jul": 1.0})[0]
    assert note["source_url"].startswith("https://crops.extension.iastate.edu/")
    assert note["source_name"] and note["text"]
