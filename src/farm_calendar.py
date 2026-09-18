"""Smart farm calendar engine (see ../ARCHITECTURE.md, "Future: the field
calendar", and the plan in the Layer 3 follow-up).

Turns "a thing the farmer has + a date anchoring it" into "what is due and
when", for any enterprise: crops, cattle, sheep, later others. The knowledge
lives as data in calendar_knowledge/*.json; this module is just the engine.

SOURCING: same rule as advice_sources.py -- a rule with no citation does not
load. `validate_rule()` enforces it mechanically (real source URL on an
extension/university/government host, health items flagged vet_confirm, no
dosage text), and `load_rules()` raises rather than silently skipping a bad
rule, so a bad entry can't quietly ship.

Two trigger kinds:
- "offset": anchor event + N days (animals, calendar-driven tasks); N may be
  negative for "N days BEFORE the anchor" (e.g. vaccinate ewes before an
  expected lambing date), and an optional window_days widens the due date
  into a range (sources publish "3 to 4 weeks", not a single day). Handled
  here.
- "gdd": a crop growth stage from growth_stages.py, projected forward from
  heat accumulation. The projection needs Earth Engine and lives in
  stage_projection.py; the caller passes its result in as
  subject["stage_projection"] ({stage_code: {from, likely, to}}). Without a
  projection for that stage (no planting date, too little history, stage
  already reached) plan_calendar() emits nothing rather than guessing.

Missing anchors never produce a guessed date; missing_anchors() reports what
the farmer still needs to enter so the UI can ask for it.
"""
import json
import re
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

KNOWLEDGE_DIR = Path(__file__).resolve().parent / "calendar_knowledge"

CATEGORIES = {"crop_stage", "health", "breeding", "husbandry", "harvest"}
TRIGGER_TYPES = {"offset", "gdd"}
CONFIDENCES = {"good", "approximate"}

# Extension services are .edu (ISU, Purdue, ...) or extension.org; federal
# sources are .gov. Widen deliberately, one host at a time, not by wildcard.
ALLOWED_SOURCE_SUFFIXES = (".edu", ".gov")
ALLOWED_SOURCE_HOSTS = {"extension.org", "www.extension.org"}

# Reminders only, never dosing (health items are vet-confirm). A number
# followed by a dose-like unit in the guidance text is rejected outright.
DOSAGE_RE = re.compile(r"\b\d+(\.\d+)?\s?(mg|mcg|ml|cc|iu|oz|lbs?)\b", re.IGNORECASE)

DUE_SOON_DAYS = 14
MAX_REPEATS = 50

REQUIRED_FIELDS = (
    "id", "subject_kind", "category", "title", "guidance", "trigger",
    "source_name", "source_url", "confidence", "vet_confirm",
)


def _valid_source_url(url: str) -> bool:
    parsed = urlparse(url or "")
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host:
        return False
    return host in ALLOWED_SOURCE_HOSTS or host.endswith(ALLOWED_SOURCE_SUFFIXES)


def validate_rule(rule: dict) -> list:
    """Every problem with a rule, as readable strings ([] means valid)."""
    problems = []
    rid = rule.get("id", "<no id>")
    for field in REQUIRED_FIELDS:
        if field not in rule or rule[field] in (None, ""):
            problems.append(f"{rid}: missing '{field}'")
    if problems:
        return problems

    if rule["category"] not in CATEGORIES:
        problems.append(f"{rid}: unknown category '{rule['category']}'")
    if rule["confidence"] not in CONFIDENCES:
        problems.append(f"{rid}: unknown confidence '{rule['confidence']}'")
    if not _valid_source_url(rule["source_url"]):
        problems.append(
            f"{rid}: source_url must be https on an extension/.edu/.gov host, got '{rule['source_url']}'"
        )
    if rule["category"] == "health" and rule["vet_confirm"] is not True:
        problems.append(f"{rid}: health rules must set vet_confirm true")
    if DOSAGE_RE.search(rule["guidance"]) or DOSAGE_RE.search(rule["title"]):
        problems.append(f"{rid}: guidance/title contains dosage-like text; reminders only")

    trigger = rule["trigger"]
    ttype = trigger.get("type") if isinstance(trigger, dict) else None
    if ttype not in TRIGGER_TYPES:
        problems.append(f"{rid}: unknown trigger type '{ttype}'")
    elif ttype == "offset":
        if not trigger.get("anchor"):
            problems.append(f"{rid}: offset trigger needs 'anchor'")
        if not isinstance(trigger.get("days"), int):
            problems.append(f"{rid}: offset trigger needs integer 'days' (negative = before anchor)")
        window = trigger.get("window_days")
        if window is not None and (not isinstance(window, int) or window < 0):
            problems.append(f"{rid}: 'window_days' must be an integer >= 0")
        repeat = trigger.get("repeat_every_days")
        if repeat is not None:
            if not isinstance(repeat, int) or repeat <= 0:
                problems.append(f"{rid}: 'repeat_every_days' must be a positive integer")
            if not isinstance(trigger.get("until_days"), int):
                problems.append(f"{rid}: repeating rules need integer 'until_days'")
    elif ttype == "gdd":
        if not trigger.get("stage"):
            problems.append(f"{rid}: gdd trigger needs 'stage'")
        else:
            from growth_stages import stage_model
            model = stage_model(rule["subject_kind"])
            if model is None:
                problems.append(f"{rid}: no growth-stage model for '{rule['subject_kind']}'")
            elif trigger["stage"] not in {code for _, code, _ in model["stages"]}:
                problems.append(f"{rid}: '{trigger['stage']}' is not a stage in the {rule['subject_kind']} model")
    return problems


def load_rules(directory: Path = KNOWLEDGE_DIR) -> list:
    """All rules from calendar_knowledge/*.json. Raises ValueError listing
    every problem rather than skipping bad rules -- a bad entry must be
    fixed, not silently dropped."""
    rules, problems, seen = [], [], set()
    for path in sorted(Path(directory).glob("*.json")):
        for rule in json.loads(path.read_text()).get("rules", []):
            problems.extend(f"{path.name}: {p}" for p in validate_rule(rule))
            if rule.get("id") in seen:
                problems.append(f"{path.name}: duplicate rule id '{rule.get('id')}'")
            seen.add(rule.get("id"))
            rules.append(rule)
    if problems:
        raise ValueError("Invalid calendar knowledge:\n" + "\n".join(problems))
    return rules


def _to_date(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(value)


def offset_occurrences(trigger: dict, anchor_date: date) -> list:
    """Due dates for an offset trigger: anchor + days, then every
    repeat_every_days while the offset stays within until_days."""
    days = trigger["days"]
    repeat = trigger.get("repeat_every_days")
    if not repeat:
        return [anchor_date + timedelta(days=days)]
    until = trigger["until_days"]
    out = []
    while days <= until and len(out) < MAX_REPEATS:
        out.append(anchor_date + timedelta(days=days))
        days += repeat
    return out


def status_for(due: date, today: date, done: bool) -> str:
    if done:
        return "done"
    if due < today:
        return "overdue"
    if (due - today).days <= DUE_SOON_DAYS:
        return "due_soon"
    return "upcoming"


def _entry(subject, rule, due_from, due_likely, due_to, status, **extra):
    return {
        "subject_type": subject["subject_type"],
        "subject_id": subject["subject_id"],
        "subject_name": subject.get("name"),
        "rule_id": rule["id"],
        "title": rule["title"],
        "category": rule["category"],
        "due_from": due_from,
        "due_likely": due_likely,
        "due_to": due_to,
        "status": status,
        "guidance": rule["guidance"],
        "source_name": rule["source_name"],
        "source_url": rule["source_url"],
        "confidence": rule["confidence"],
        "caveat": rule.get("caveat"),
        "vet_confirm": rule["vet_confirm"],
        **extra,
    }


def _gdd_entry(subject, rule, today, done_keys):
    window = (subject.get("stage_projection") or {}).get(rule["trigger"]["stage"])
    if not window or not window.get("likely"):
        return None
    key = (subject["subject_type"], str(subject["subject_id"]), rule["id"], window["likely"])
    status = status_for(_to_date(window["likely"]), today, key in done_keys)
    return _entry(subject, rule, window["from"], window["likely"], window["to"], status, projected=True)


def plan_calendar(subjects: list, rules: list, today, completions=None) -> list:
    """Calendar entries, sorted by date, for every offset rule whose anchor
    the subject has, plus every gdd rule the subject has a projected window for.

    `subjects`: [{"subject_type": "herd"|"field", "subject_id": ..., "kind":
    "cattle"|"sheep"|"corn"..., "name": str, "anchors": {anchor_kind:
    ISO date or date}}] -- the latest date per anchor kind.
    `completions`: iterable of (subject_type, subject_id, rule_id,
    occurrence ISO date) the farmer has ticked off.
    """
    today = _to_date(today)
    done_keys = {(t, str(i), r, str(d)) for t, i, r, d in (completions or [])}
    entries = []
    for subject in subjects:
        for rule in rules:
            trigger = rule["trigger"]
            if rule["subject_kind"] != subject["kind"]:
                continue
            if trigger["type"] == "gdd":
                entry = _gdd_entry(subject, rule, today, done_keys)
                if entry:
                    entries.append(entry)
                continue
            anchor = subject.get("anchors", {}).get(trigger["anchor"])
            if not anchor:
                continue
            window = timedelta(days=trigger.get("window_days", 0))
            for due in offset_occurrences(trigger, _to_date(anchor)):
                key = (subject["subject_type"], str(subject["subject_id"]), rule["id"], due.isoformat())
                entries.append(_entry(
                    subject, rule, due.isoformat(), due.isoformat(), (due + window).isoformat(),
                    status_for(due, today, key in done_keys), projected=False,
                ))
    entries.sort(key=lambda e: (e["due_likely"], e["title"]))
    return entries


def missing_anchors(subjects: list, rules: list) -> list:
    """Offset rules a subject matches but can't schedule yet because its
    anchor date hasn't been entered -- lets the UI ask for it instead of
    the engine guessing."""
    missing, seen = [], set()
    for subject in subjects:
        for rule in rules:
            trigger = rule["trigger"]
            if trigger["type"] != "offset" or rule["subject_kind"] != subject["kind"]:
                continue
            if subject.get("anchors", {}).get(trigger["anchor"]):
                continue
            key = (subject["subject_type"], str(subject["subject_id"]), trigger["anchor"])
            if key in seen:
                continue
            seen.add(key)
            missing.append({
                "subject_type": subject["subject_type"],
                "subject_id": subject["subject_id"],
                "subject_name": subject.get("name"),
                "anchor": trigger["anchor"],
            })
    return missing
