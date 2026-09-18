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
- "offset": anchor event + N days (animals, calendar-driven tasks). Handled
  here.
- "gdd": a crop growth stage from growth_stages.py, projected forward from
  heat accumulation. Loaded and validated here, but the projection needs
  Earth Engine and lives with the crop path (field_insights.py), so
  plan_calendar() skips gdd rules rather than guessing a date for them.

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
        if not isinstance(trigger.get("days"), int) or trigger["days"] < 0:
            problems.append(f"{rid}: offset trigger needs integer 'days' >= 0")
        repeat = trigger.get("repeat_every_days")
        if repeat is not None:
            if not isinstance(repeat, int) or repeat <= 0:
                problems.append(f"{rid}: 'repeat_every_days' must be a positive integer")
            if not isinstance(trigger.get("until_days"), int):
                problems.append(f"{rid}: repeating rules need integer 'until_days'")
    elif ttype == "gdd":
        if not trigger.get("stage"):
            problems.append(f"{rid}: gdd trigger needs 'stage'")
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


def plan_calendar(subjects: list, rules: list, today, completions=None) -> list:
    """Calendar entries, sorted by date, for every offset rule whose anchor
    the subject has.

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
            if trigger["type"] != "offset" or rule["subject_kind"] != subject["kind"]:
                continue
            anchor = subject.get("anchors", {}).get(trigger["anchor"])
            if not anchor:
                continue
            for due in offset_occurrences(trigger, _to_date(anchor)):
                key = (subject["subject_type"], str(subject["subject_id"]), rule["id"], due.isoformat())
                entries.append({
                    "subject_type": subject["subject_type"],
                    "subject_id": subject["subject_id"],
                    "subject_name": subject.get("name"),
                    "rule_id": rule["id"],
                    "title": rule["title"],
                    "category": rule["category"],
                    "due_from": due.isoformat(),
                    "due_likely": due.isoformat(),
                    "due_to": due.isoformat(),
                    "status": status_for(due, today, key in done_keys),
                    "guidance": rule["guidance"],
                    "source_name": rule["source_name"],
                    "source_url": rule["source_url"],
                    "confidence": rule["confidence"],
                    "caveat": rule.get("caveat"),
                    "vet_confirm": rule["vet_confirm"],
                })
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
