"""Service + route: projection failures degrade to notes, knowledge summary
is right, and POST /calendar/plan validates input. No Earth Engine."""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

import calendar_service as cs

import pytest

TODAY = date(2026, 9, 18)


@pytest.fixture(autouse=True)
def _fresh_projection_cache():
    cs._PROJECTION_CACHE.clear()
    yield
    cs._PROJECTION_CACHE.clear()
BOUNDARY = {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [0, 0]]]}


def field(**kw):
    base = {"subject_type": "field", "subject_id": 1, "kind": "corn", "name": "North",
            "anchors": {}, "boundary": BOUNDARY, "planting_date": "2026-05-10"}
    base.update(kw)
    return base


def fake_projector(boundary, crop, planting, as_of):
    return {"stages": {"R6": {"from": "2026-09-25", "likely": "2026-09-28", "to": "2026-10-01"}}}


def test_knowledge_summary_lists_anchors_and_stage_rules():
    k = cs.knowledge_summary()
    assert "lambed" in k["sheep"]["anchors"] and "breeding_start" in k["cattle"]["anchors"]
    assert k["corn"]["stage_rules"] is True and k["corn"]["anchors"] == []


def test_field_gets_projected_entries():
    plan = cs.build_plan([field()], as_of=TODAY, projector=fake_projector)
    assert [e["rule_id"] for e in plan["entries"]] == ["corn_physiological_maturity"]
    assert plan["notes"] == []


def test_projection_error_becomes_a_note_not_a_failure():
    def refuse(*a):
        return {"error": "no_stage_model", "message": "no model"}
    plan = cs.build_plan([field()], as_of=TODAY, projector=refuse)
    assert plan["entries"] == [] and plan["notes"][0]["code"] == "no_stage_model"


def test_projector_exception_degrades_gracefully():
    def boom(*a):
        raise RuntimeError("EE down")
    plan = cs.build_plan([field()], as_of=TODAY, projector=boom)
    assert plan["notes"][0]["code"] == "projection_unavailable"


def test_missing_planting_date_asks_for_it():
    plan = cs.build_plan([field(planting_date=None)], as_of=TODAY, projector=fake_projector)
    assert plan["notes"][0]["code"] == "needs_planting_date"


def test_unknown_kind_is_flagged():
    herd = {"subject_type": "herd", "subject_id": 9, "kind": "goats", "anchors": {}}
    plan = cs.build_plan([herd], as_of=TODAY)
    assert plan["notes"][0]["code"] == "no_knowledge"


def test_herd_without_anchor_reports_missing_anchor():
    herd = {"subject_type": "herd", "subject_id": 2, "kind": "sheep", "name": "Ewes", "anchors": {}}
    plan = cs.build_plan([herd], as_of=TODAY)
    assert {m["anchor"] for m in plan["missing_anchors"]} == {"lambing_due", "lambed"}


# --- route -------------------------------------------------------------------

def client():
    from api.main import app
    return TestClient(app)


def test_route_plans_a_flock():
    body = {"subjects": [{"subject_type": "herd", "subject_id": 2, "kind": "sheep", "name": "Ewes",
                          "anchors": {"lambed": "2026-08-01"}}]}
    r = client().post("/calendar/plan", json=body)
    assert r.status_code == 200
    ids = {e["rule_id"] for e in r.json()["entries"]}
    assert {"sheep_lamb_weaning", "sheep_lamb_clostridial_first_dose"} <= ids


def test_route_rejects_bad_anchor_date():
    body = {"subjects": [{"subject_type": "herd", "subject_id": 2, "kind": "sheep",
                          "anchors": {"lambed": "not-a-date"}}]}
    assert client().post("/calendar/plan", json=body).status_code == 422


def test_route_rejects_unknown_subject_type():
    body = {"subjects": [{"subject_type": "barn", "subject_id": 2, "kind": "sheep"}]}
    assert client().post("/calendar/plan", json=body).status_code == 422


def test_route_knowledge():
    r = client().get("/calendar/knowledge")
    assert r.status_code == 200 and "cattle" in r.json()


def test_projections_are_cached_and_errors_are_not():
    cs._PROJECTION_CACHE.clear()
    calls = []

    def counting(boundary, crop, planting, as_of):
        calls.append(1)
        return fake_projector(boundary, crop, planting, as_of)

    cs.build_plan([field()], as_of=TODAY, projector=counting)
    cs.build_plan([field()], as_of=TODAY, projector=counting)
    assert len(calls) == 1  # second plan served from cache

    cs._PROJECTION_CACHE.clear()
    flaky = []

    def fails_once(*a):
        flaky.append(1)
        return {"error": "no_temperature_data", "message": "x"}

    cs.build_plan([field()], as_of=TODAY, projector=fails_once)
    cs.build_plan([field()], as_of=TODAY, projector=fails_once)
    assert len(flaky) == 2  # errors retried, never cached


def test_many_fields_all_get_projected():
    cs._PROJECTION_CACHE.clear()
    fields = [field(subject_id=i, planting_date=f"2026-05-{10 + i:02d}") for i in range(1, 6)]
    plan = cs.build_plan(fields, as_of=TODAY, projector=fake_projector)
    assert len(plan["entries"]) == 5 and plan["notes"] == []
