"""Glue between the pure calendar engine (farm_calendar.py) and the outside
world: for crop fields it fetches a stage projection (Earth Engine, via
stage_projection.py); for herds it just passes the farmer's anchor dates
through. Sits behind POST /calendar/plan.

Everything that can fail per-subject (no planting date, no staging model,
Earth Engine hiccup) becomes a `notes` entry and that subject simply gets no
projected items -- one bad field never sinks the whole calendar, and a
missing projection is never papered over with a guessed date.
"""
from datetime import date

from farm_calendar import load_rules, missing_anchors, plan_calendar

_RULES = None


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


def build_plan(subjects: list, completions: list = None, as_of: date = None, projector=None) -> dict:
    """`subjects`: dicts with subject_type/subject_id/kind/name/anchors, and
    for fields also boundary + planting_date. `projector` is injectable so
    tests don't need Earth Engine."""
    as_of = as_of or date.today()
    projector = projector or _default_projector
    known = knowledge_summary()
    notes, prepared = [], []

    for subject in subjects:
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
                try:
                    projection = projector(boundary, subject["kind"], planting, as_of)
                except Exception:  # Earth Engine / network -- degrade, don't fail the whole plan
                    projection = {"error": "projection_unavailable",
                                  "message": "Growth-stage projection is temporarily unavailable."}
                if "error" in projection:
                    notes.append({"subject_id": subject["subject_id"], "code": projection["error"],
                                  "message": projection["message"]})
                else:
                    subject["stage_projection"] = projection["stages"]
        prepared.append(subject)

    all_rules = rules()
    entries = plan_calendar(prepared, all_rules, as_of, completions=completions)
    return {
        "as_of": as_of.isoformat(),
        "entries": entries,
        "missing_anchors": missing_anchors(prepared, all_rules),
        "notes": notes,
    }
