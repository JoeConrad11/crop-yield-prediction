"use client";

import { useMemo, useState } from "react";
import { useQueries } from "@tanstack/react-query";
import { BookOpen, CalendarDays, Check, Stethoscope } from "lucide-react";

import { fetchCalendarPlan } from "@/lib/api-client";
import { addFarmEvent, setCompletion } from "@/lib/farm-client";
import type { CalendarCompletion, FarmEvent, Field, Herd } from "@/lib/farm-types";
import type { CalendarEntry, CalendarMissingAnchor, CalendarNote, CalendarSubject } from "@/lib/types";
import { formatDay, formatRange } from "@/lib/calendar-labels";
import { CalendarGrid, isoDay, type DayItem } from "./calendar-grid";
import { CalendarSuggestions } from "./calendar-suggestions";

const completionKey = (type: string, id: number, ruleId: string, date: string) => `${type}:${id}:${ruleId}:${date}`;

// The smart farm calendar: what's due, when, and why -- for crops and
// livestock alike. Dates are derived server-side (POST /calendar/plan) from
// the farmer's fields, herds and anchor dates plus cited knowledge; this
// component only lays them out and records "done" ticks. Ticks are applied
// client-side so checking an item off doesn't re-run the Earth Engine stage
// projections behind the crop dates.
export function FarmCalendar({
  farmId,
  fields,
  herds,
  events,
  completions,
  onChanged,
}: {
  farmId: number;
  fields: Field[];
  herds: Herd[];
  events: FarmEvent[];
  completions: CalendarCompletion[];
  onChanged: () => Promise<void> | void;
}) {
  const subjects = useMemo<CalendarSubject[]>(() => {
    const cropFields: CalendarSubject[] = fields
      .filter((f) => f.primary_crop)
      .map((f) => ({
        subject_type: "field",
        subject_id: f.id,
        kind: f.primary_crop as string,
        name: f.name,
        boundary: f.boundary,
        planting_date: f.planting_date,
      }));
    const herdSubjects: CalendarSubject[] = herds.map((h) => {
      // Latest date per kind wins -- events are ordered newest first.
      const anchors: Record<string, string> = {};
      for (const e of events) {
        if (e.subject_type === "herd" && e.subject_id === h.id && !(e.kind in anchors)) {
          anchors[e.kind] = e.event_date;
        }
      }
      return { subject_type: "herd", subject_id: h.id, kind: h.species, name: h.name, anchors };
    });
    return [...cropFields, ...herdSubjects];
  }, [fields, herds, events]);

  // One request per field/herd (not one big request): livestock come back
  // instantly and crop dates fill in as their Earth Engine projections
  // finish, and each result is cached for the day.
  const results = useQueries({
    queries: subjects.map((subject) => ({
      queryKey: ["calendar-plan", JSON.stringify(subject)],
      queryFn: () => fetchCalendarPlan([subject]),
      staleTime: 12 * 60 * 60 * 1000,
      retry: 1,
    })),
  });
  const loadingCount = results.filter((r) => r.isLoading).length;
  const anyError = results.some((r) => r.isError);
  const plans = results.flatMap((r) => (r.data ? [r.data] : []));
  const allEntries: CalendarEntry[] = plans.flatMap((p) => p.entries);
  const missingAnchors: CalendarMissingAnchor[] = plans.flatMap((p) => p.missing_anchors);
  const notes: CalendarNote[] = plans.flatMap((p) => p.notes);

  const doneKeys = useMemo(
    () => new Set(completions.map((c) => completionKey(c.subject_type, c.subject_id, c.rule_id, c.occurrence_date))),
    [completions]
  );

  const [busyKey, setBusyKey] = useState<string | null>(null);

  async function toggle(entry: CalendarEntry, done: boolean) {
    const key = completionKey(entry.subject_type, entry.subject_id, entry.rule_id, entry.due_likely);
    setBusyKey(key);
    try {
      await setCompletion({
        farmId,
        subjectType: entry.subject_type,
        subjectId: entry.subject_id,
        ruleId: entry.rule_id,
        occurrenceDate: entry.due_likely,
        done,
      });
      await onChanged();
    } finally {
      setBusyKey(null);
    }
  }

  async function addAnchor(m: CalendarMissingAnchor, date: string) {
    await addFarmEvent({
      farmId,
      subjectType: m.subject_type,
      subjectId: m.subject_id,
      kind: m.anchor,
      eventDate: date,
    });
    await onChanged();
  }

  const today = useMemo(() => isoDay(new Date()), []);
  const [view, setView] = useState(() => {
    const t = new Date();
    return { year: t.getFullYear(), month: t.getMonth() };
  });
  const [selected, setSelected] = useState(today);

  const entries = allEntries
    .map((e) => ({ entry: e, done: doneKeys.has(completionKey(e.subject_type, e.subject_id, e.rule_id, e.due_likely)) }))
    .sort((a, b) => a.entry.due_likely.localeCompare(b.entry.due_likely));

  // Each item sits on its likely day; other days inside its date range are
  // marked as "window" so a projected range is visible on the grid.
  const itemsByDay = useMemo(() => {
    const map: Record<string, DayItem[]> = {};
    const add = (iso: string, item: DayItem) => (map[iso] ??= []).push(item);
    for (const { entry, done } of entries) {
      add(entry.due_likely, { entry, kind: "likely", done });
      const from = new Date(`${entry.due_from}T00:00:00`);
      const to = new Date(`${entry.due_to}T00:00:00`);
      for (let d = new Date(from), n = 0; d <= to && n < 31; d.setDate(d.getDate() + 1), n++) {
        const iso = isoDay(d);
        if (iso !== entry.due_likely) add(iso, { entry, kind: "window", done });
      }
    }
    return map;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allEntries.length, doneKeys]);

  const open = entries.filter((x) => !x.done).map((x) => x.entry);
  const groups: { title: string; items: CalendarEntry[]; collapsed?: boolean }[] = [
    { title: "Overdue", items: open.filter((e) => e.status === "overdue") },
    { title: "Next 2 weeks", items: open.filter((e) => e.status === "due_soon") },
    { title: "Later", items: open.filter((e) => e.status === "upcoming"), collapsed: true },
  ];
  const doneItems = entries.filter((x) => x.done).map((x) => x.entry);
  const selectedItems = itemsByDay[selected] ?? [];

  const entryCard = (e: CalendarEntry, done: boolean) => {
    const key = completionKey(e.subject_type, e.subject_id, e.rule_id, e.due_likely);
    return <EntryCard key={key} entry={e} done={done} busy={busyKey === key} onToggle={(d) => toggle(e, d)} />;
  };

  return (
    <section className="space-y-3">
      <h2 className="flex items-center gap-2 font-heading text-lg font-semibold text-foreground">
        <CalendarDays className="size-4 text-primary" aria-hidden="true" />
        Calendar
      </h2>

      <CalendarSuggestions
        missingAnchors={missingAnchors}
        notes={notes}
        hasAnything={subjects.length > 0}
        onAddAnchor={addAnchor}
      />

      {loadingCount > 0 && (
        <p className="text-xs text-muted-foreground">
          Working out crop dates for {loadingCount} {loadingCount === 1 ? "field" : "fields"} -- this can take about
          15 seconds the first time. Everything else is already shown.
        </p>
      )}
      {anyError && (
        <p className="text-xs text-destructive">Some items couldn&apos;t be loaded right now. Please try again shortly.</p>
      )}

      <CalendarGrid
        year={view.year}
        month={view.month}
        onMonthChange={(year, month) => setView({ year, month })}
        itemsByDay={itemsByDay}
        selected={selected}
        onSelect={setSelected}
        today={today}
      />

      <div className="space-y-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {selected === today ? "Today" : formatDay(selected, true)}
        </h3>
        {selectedItems.length ? (
          <ul className="space-y-2">{selectedItems.map((x) => entryCard(x.entry, x.done))}</ul>
        ) : (
          <p className="text-sm text-muted-foreground">Nothing scheduled for this day.</p>
        )}
      </div>

      {groups.map(
        (g) =>
          !!g.items.length &&
          (g.collapsed ? (
            <details key={g.title}>
              <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {g.title} ({g.items.length})
              </summary>
              <ul className="mt-2 space-y-2">{g.items.map((e) => entryCard(e, false))}</ul>
            </details>
          ) : (
            <div key={g.title} className="space-y-2">
              <h3
                className={`text-xs font-semibold uppercase tracking-wide ${
                  g.title === "Overdue" ? "text-destructive" : "text-muted-foreground"
                }`}
              >
                {g.title}
              </h3>
              <ul className="space-y-2">{g.items.map((e) => entryCard(e, false))}</ul>
            </div>
          ))
      )}

      {!!doneItems.length && (
        <details>
          <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Done ({doneItems.length})
          </summary>
          <ul className="mt-2 space-y-2">{doneItems.map((e) => entryCard(e, true))}</ul>
        </details>
      )}
    </section>
  );
}

function EntryCard({
  entry,
  done,
  busy,
  onToggle,
}: {
  entry: CalendarEntry;
  done: boolean;
  busy: boolean;
  onToggle: (done: boolean) => void;
}) {
  const overdue = entry.status === "overdue" && !done;
  return (
    <li
      className={`rounded-xl border bg-card px-4 py-3 shadow-sm ${
        overdue ? "border-destructive/40" : "border-accent/40"
      } ${done ? "opacity-60" : ""}`}
    >
      <div className="flex items-start gap-3">
        <button
          type="button"
          role="checkbox"
          aria-checked={done}
          aria-label={`Mark "${entry.title}" ${done ? "not done" : "done"}`}
          disabled={busy}
          onClick={() => onToggle(!done)}
          className={`mt-0.5 flex size-5 shrink-0 cursor-pointer items-center justify-center rounded border transition-colors ${
            done ? "border-primary bg-primary text-primary-foreground" : "border-border hover:border-primary"
          }`}
        >
          {done && <Check className="size-3.5" aria-hidden="true" />}
        </button>
        <div className="min-w-0 flex-1 text-sm">
          <p className={`font-medium text-card-foreground ${done ? "line-through" : ""}`}>{entry.title}</p>
          <p className="text-xs text-muted-foreground">
            {entry.subject_name ? `${entry.subject_name} · ` : ""}
            {formatRange(entry.due_from, entry.due_to)}
            {entry.projected && " · projected from your field's heat so far"}
          </p>
          <p className="mt-1.5 text-xs text-muted-foreground">{entry.guidance}</p>
          {entry.vet_confirm && (
            <p className="mt-1.5 flex items-center gap-1 text-xs font-medium text-foreground">
              <Stethoscope className="size-3.5 text-primary" aria-hidden="true" />
              A reminder, not veterinary advice -- confirm with your vet and follow the product label.
            </p>
          )}
          {entry.caveat && <p className="mt-1 text-[11px] text-muted-foreground/80">{entry.caveat}</p>}
          <a
            href={entry.source_url}
            target="_blank"
            rel="noreferrer"
            className="mt-1 inline-flex items-center gap-1 text-[11px] text-muted-foreground/80 underline decoration-dotted hover:text-muted-foreground"
          >
            <BookOpen className="size-3" aria-hidden="true" />
            Source: {entry.source_name}
          </a>
        </div>
      </div>
    </li>
  );
}
