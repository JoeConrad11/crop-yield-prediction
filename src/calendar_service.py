"""Glue between the pure calendar engine (farm_calendar.py) and the outside
world: for crop fields it fetches a stage projection (Earth Engine, via
stage_projection.py); for herds it just passes the farmer's anchor dates
through. Sits behind POST /calendar/plan.

Everything that can fail per-subject (no planting date, no staging model,
Earth Engine hiccup) becomes a `notes` entry and that subject simply gets no
projected items -- one bad field never sinks the whole calendar, and a
missing projection is never papered over with a guessed date.
"""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from farm_calendar import load_rules, missing_anchors, plan_calendar

_RULES = None

# Earth Engine projections take ~7-10s per field, so they run in parallel and
# successful results are cached per (boundary, crop, planting date, day) for
# as long as this container lives -- reopening the calendar is then instant.
# Errors are never cached, so a transient failure retries.
_PROJECTION_CACHE = {}
MAX_PROJECTION_WORKERS = 6


def rules():
    global _RULES
    if _RULES is None:
        _RULES = load_rules()
    return _RULES


def knowledge_summary() -> dict:
    """What the calendar knows, per subject kind: which anchor dates it can
    use (so the UI knows what to ask for) and how many rules exist."""
    out = {}
    for rule in rules():
        entry = out.setdefault(rule["subject_kind"], {"anchors": set(), "rule_count": 0, "stage_rules": False})
        entry["rule_count"] += 1
        if rule["trigger"]["type"] == "offset":
            entry["anchors"].add(rule["trigger"]["anchor"])
        else:
            entry["stage_rules"] = True
    return {k: {**v, "anchors": sorted(v["anchors"])} for k, v in sorted(out.items())}


def _default_projector(boundary, crop, planting_date, as_of):
    from stage_projection import field_stage_projection
    return field_stage_projection(boundary, crop, planting_date, as_of)


def _project_cached(projector, boundary, crop, planting_date, as_of):
    key = (json.dumps(boundary, sort_keys=True), crop, planting_date, as_of.isoformat())
    if key in _PROJECTION_CACHE:
        return _PROJECTION_CACHE[key]
    try:
        result = projector(boundary, crop, planting_date, as_of)
    except Exception:  # Earth Engine / network -- degrade, don't fail the whole plan
        return {"error": "projection_unavailable",
                "message": "Growth-stage projection is temporarily unavailable."}
    if "error" not in result:
        _PROJECTION_CACHE[key] = result
    return result


def build_plan(subjects: list, completions: list = None, as_of: date = None, projector=None) -> dict:
    """`subjects`: dicts with subject_type/subject_id/kind/name/anchors, and
    for fields also boundary + planting_date. `projector` is injectable so
    tests don't need Earth Engine."""
    as_of = as_of or date.today()
    projector = projector or _default_projector
    known = knowledge_summary()
    notes, prepared, jobs = [], [], {}

    for index, subject in enumerate(subjects):
        subject = dict(subject)
        label = subject.get("name") or f"{subject['subject_type']} {subject['subject_id']}"
        if subject["kind"] not in known:
            notes.append({"subject_id": subject["subject_id"], "code": "no_knowledge",
                          "message": f"The calendar has no schedules for '{subject['kind']}' yet."})
        elif subject["subject_type"] == "field" and known[subject["kind"]]["stage_rules"]:
            boundary, planting = subject.pop("boundary", None), subject.get("planting_date")
            if not boundary or not planting:
                notes.append({"subject_id": subject["subject_id"], "code": "needs_planting_date",
                              "message": f"Add a boundary and planting date for {label} to project its growth stages."})
            else:
                jobs[index] = (boundary, subject["kind"], planting)
        prepared.append(subject)

    if jobs:
        with ThreadPoolExecutor(max_workers=min(MAX_PROJECTION_WORKERS, len(jobs))) as pool:
            futures = {i: pool.submit(_project_cached, projector, *args, as_of) for i, args in jobs.items()}
        for i, future in futures.items():
            projection = future.result()
            if "error" in projection:
                notes.append({"subject_id": prepared[i]["subject_id"], "code": projection["error"],
                              "message": projection["message"]})
            else:
                prepared[i]["stage_projection"] = projection["stages"]

    all_rules = rules()
    entries = plan_calendar(prepared, all_rules, as_of, completions=completions)
    return {
        "as_of": as_of.isoformat(),
        "entries": entries,
        "missing_anchors": missing_anchors(prepared, all_rules),
        "notes": notes,
    }
