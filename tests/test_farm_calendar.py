"""Farm calendar engine: rule validation (the sourcing rule, mechanically),
offset expansion, statuses, and refusal to guess when an anchor is missing."""
import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import farm_calendar as fc

TODAY = date(2026, 9, 18)


def make_rule(**overrides):
    rule = {
        "id": "sheep_test_rule",
        "subject_kind": "sheep",
        "category": "husbandry",
        "title": "Wean lambs",
        "guidance": "Lambs are commonly weaned at roughly 60 to 90 days of age.",
        "trigger": {"type": "offset", "anchor": "lambed", "days": 60},
        "source_name": "Example State University Extension",
        "source_url": "https://extension.example.edu/sheep/weaning",
        "confidence": "good",
        "vet_confirm": False,
    }
    rule.update(overrides)
    return rule


def flock(**anchors):
    return {"subject_type": "herd", "subject_id": 1, "kind": "sheep", "name": "Ewes", "anchors": anchors}


# --- validation / sourcing rule -------------------------------------------

def test_valid_rule_has_no_problems():
    assert fc.validate_rule(make_rule()) == []


@pytest.mark.parametrize("url", [
    "", "http://extension.example.edu/x", "https://blog.example.com/x", "https://example.org/x",
])
def test_rejects_unsourced_or_untrusted_urls(url):
    assert fc.validate_rule(make_rule(source_url=url))


def test_accepts_gov_and_extension_org_hosts():
    assert fc.validate_rule(make_rule(source_url="https://www.usda.gov/x")) == []
    assert fc.validate_rule(make_rule(source_url="https://www.extension.org/x")) == []


def test_health_rules_must_be_vet_confirm():
    bad = make_rule(category="health", vet_confirm=False)
    assert any("vet_confirm" in p for p in fc.validate_rule(bad))
    assert fc.validate_rule(make_rule(category="health", vet_confirm=True)) == []


@pytest.mark.parametrize("text", [
    "Give 5 mg per kg", "Administer 10 ml under the skin", "Use 2cc", "Feed 3 lbs daily",
])
def test_rejects_dosage_text(text):
    assert any("dosage" in p for p in fc.validate_rule(make_rule(guidance=text)))


def test_missing_required_field_reported():
    rule = make_rule()
    del rule["source_name"]
    assert any("source_name" in p for p in fc.validate_rule(rule))


def test_repeating_rule_needs_until():
    trig = {"type": "offset", "anchor": "purchased", "days": 0, "repeat_every_days": 30}
    assert any("until_days" in p for p in fc.validate_rule(make_rule(trigger=trig)))


def test_unknown_trigger_type_rejected():
    assert fc.validate_rule(make_rule(trigger={"type": "moon"}))


# --- loading ---------------------------------------------------------------

def test_shipped_knowledge_files_are_valid():
    """The real calendar_knowledge/*.json must always load clean."""
    fc.load_rules()


def test_load_rules_raises_on_bad_rule(tmp_path):
    (tmp_path / "x.json").write_text(json.dumps({"rules": [make_rule(source_url="")]}))
    with pytest.raises(ValueError, match="source_url"):
        fc.load_rules(tmp_path)


def test_load_rules_rejects_duplicate_ids(tmp_path):
    (tmp_path / "x.json").write_text(json.dumps({"rules": [make_rule(), make_rule()]}))
    with pytest.raises(ValueError, match="duplicate"):
        fc.load_rules(tmp_path)


# --- expansion / status ----------------------------------------------------

def test_single_offset_occurrence():
    trig = {"type": "offset", "anchor": "lambed", "days": 60}
    assert fc.offset_occurrences(trig, date(2026, 4, 1)) == [date(2026, 5, 31)]


def test_repeating_occurrences_respect_until():
    trig = {"type": "offset", "anchor": "purchased", "days": 0, "repeat_every_days": 30, "until_days": 90}
    assert fc.offset_occurrences(trig, date(2026, 1, 1)) == [
        date(2026, 1, 1), date(2026, 1, 31), date(2026, 3, 2), date(2026, 4, 1),
    ]


def test_status_boundaries():
    assert fc.status_for(date(2026, 9, 17), TODAY, False) == "overdue"
    assert fc.status_for(TODAY, TODAY, False) == "due_soon"
    assert fc.status_for(date(2026, 10, 2), TODAY, False) == "due_soon"   # exactly 14 days
    assert fc.status_for(date(2026, 10, 3), TODAY, False) == "upcoming"   # 15 days
    assert fc.status_for(date(2026, 9, 1), TODAY, True) == "done"


# --- planning --------------------------------------------------------------

def test_plan_builds_entry_from_anchor():
    entries = fc.plan_calendar([flock(lambed="2026-08-01")], [make_rule()], TODAY)
    assert len(entries) == 1
    e = entries[0]
    assert e["due_likely"] == "2026-09-30" and e["status"] == "due_soon"
    assert e["source_url"].startswith("https://") and e["vet_confirm"] is False


def test_plan_never_guesses_without_anchor():
    assert fc.plan_calendar([flock()], [make_rule()], TODAY) == []


def test_plan_only_matches_same_species():
    cattle = dict(flock(lambed="2026-08-01"), kind="cattle")
    assert fc.plan_calendar([cattle], [make_rule()], TODAY) == []


def test_plan_skips_gdd_rules():
    gdd = make_rule(subject_kind="corn", category="crop_stage", trigger={"type": "gdd", "stage": "R1"})
    corn = {"subject_type": "field", "subject_id": 2, "kind": "corn", "anchors": {"planted": "2026-05-01"}}
    assert fc.plan_calendar([corn], [gdd], TODAY) == []


def test_completion_marks_done_and_only_that_occurrence():
    trig = {"type": "offset", "anchor": "lambed", "days": 10, "repeat_every_days": 10, "until_days": 20}
    rule = make_rule(trigger=trig)
    done = [("herd", 1, "sheep_test_rule", "2026-08-11")]
    entries = fc.plan_calendar([flock(lambed="2026-08-01")], [rule], TODAY, completions=done)
    by_date = {e["due_likely"]: e["status"] for e in entries}
    assert by_date["2026-08-11"] == "done"
    assert by_date["2026-08-21"] == "overdue"


def test_entries_sorted_by_date():
    early = make_rule(id="early", title="B", trigger={"type": "offset", "anchor": "lambed", "days": 5})
    late = make_rule(id="late", title="A", trigger={"type": "offset", "anchor": "lambed", "days": 50})
    entries = fc.plan_calendar([flock(lambed="2026-08-01")], [late, early], TODAY)
    assert [e["rule_id"] for e in entries] == ["early", "late"]


def test_missing_anchors_reports_what_to_ask_for():
    rule = make_rule()
    assert fc.missing_anchors([flock()], [rule]) == [
        {"subject_type": "herd", "subject_id": 1, "subject_name": "Ewes", "anchor": "lambed"}
    ]
    assert fc.missing_anchors([flock(lambed="2026-08-01")], [rule]) == []


# --- negative offsets and windows -----------------------------------------

def test_negative_offset_is_before_anchor():
    trig = {"type": "offset", "anchor": "lambing_due", "days": -28}
    assert fc.offset_occurrences(trig, date(2026, 10, 29)) == [date(2026, 10, 1)]


def test_window_days_widens_due_range():
    trig = {"type": "offset", "anchor": "lambing_due", "days": -28, "window_days": 7}
    rule = make_rule(trigger=trig)
    e = fc.plan_calendar([flock(lambing_due="2026-10-29")], [rule], TODAY)[0]
    assert (e["due_from"], e["due_likely"], e["due_to"]) == ("2026-10-01", "2026-10-01", "2026-10-08")


def test_bad_window_rejected():
    trig = {"type": "offset", "anchor": "lambed", "days": 5, "window_days": -1}
    assert any("window_days" in p for p in fc.validate_rule(make_rule(trigger=trig)))


# --- shipped knowledge, end to end ------------------------------------------

def test_shipped_rules_plan_a_real_flock_and_herd():
    rules = fc.load_rules()
    subjects = [
        {"subject_type": "herd", "subject_id": 1, "kind": "sheep", "name": "Ewes",
         "anchors": {"lambing_due": "2027-03-01", "lambed": "2026-08-01"}},
        {"subject_type": "herd", "subject_id": 2, "kind": "cattle", "name": "Cows",
         "anchors": {"breeding_start": "2026-05-01"}},
    ]
    entries = fc.plan_calendar(subjects, rules, TODAY)
    ids = {e["rule_id"] for e in entries}
    assert {"sheep_ewe_clostridial_prelambing", "sheep_lamb_weaning",
            "cattle_prebreeding_vaccination", "cattle_breeding_season_end"} <= ids
    # health entries always ask for vet confirmation and carry a citation
    for e in entries:
        assert e["source_url"].startswith("https://")
        if e["category"] == "health":
            assert e["vet_confirm"] is True
