"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BookOpen, CalendarDays, Check, Stethoscope } from "lucide-react";

import { fetchCalendarPlan } from "@/lib/api-client";
import { setCompletion } from "@/lib/farm-client";
import type { CalendarCompletion, FarmEvent, Field, Herd } from "@/lib/farm-types";
import type { CalendarEntry, CalendarSubject } from "@/lib/types";
import { anchorLabel, formatRange } from "@/lib/calendar-labels";

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

  const { data: plan, isLoading, isError } = useQuery({
    queryKey: ["calendar-plan", farmId, JSON.stringify(subjects)],
    queryFn: () => fetchCalendarPlan(subjects),
    enabled: subjects.length > 0,
    staleTime: 10 * 60 * 1000,
  });

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

  const entries = (plan?.entries ?? []).map((e) => ({
    entry: e,
    done: doneKeys.has(completionKey(e.subject_type, e.subject_id, e.rule_id, e.due_likely)),
  }));
  const open = entries.filter((x) => !x.done).map((x) => x.entry);
  const groups: { title: string; items: CalendarEntry[] }[] = [
    { title: "Overdue", items: open.filter((e) => e.status === "overdue") },
    { title: "Next 2 weeks", items: open.filter((e) => e.status === "due_soon") },
    { title: "Later", items: open.filter((e) => e.status === "upcoming") },
  ];
  const doneItems = entries.filter((x) => x.done).map((x) => x.entry);

  return (
    <section className="space-y-3">
      <h2 className="flex items-center gap-2 font-heading text-lg font-semibold text-foreground">
        <CalendarDays className="size-4 text-primary" aria-hidden="true" />
        Calendar
      </h2>

      {!subjects.length && (
        <p className="rounded-xl border border-dashed border-accent/40 p-6 text-center text-sm text-muted-foreground">
          Add a field with a crop, or some livestock, and what&apos;s due will show up here.
        </p>
      )}
      {isLoading && <p className="text-sm text-muted-foreground">Working out your calendar...</p>}
      {isError && (
        <p className="text-sm text-destructive">Couldn&apos;t build your calendar right now. Please try again shortly.</p>
      )}

      {plan?.missing_anchors.map((m) => (
        <p key={`${m.subject_type}-${m.subject_id}-${m.anchor}`} className="text-xs text-muted-foreground">
          Add <span className="font-medium text-foreground">{anchorLabel(m.anchor).toLowerCase()}</span> for{" "}
          {m.subject_name ?? "this group"} to see the schedule items that depend on it.
        </p>
      ))}
      {plan?.notes.map((n, i) => (
        <p key={`${n.code}-${n.subject_id}-${i}`} className="text-xs text-muted-foreground">
          {n.message}
        </p>
      ))}

      {plan && !entries.length && !plan.missing_anchors.length && !!subjects.length && (
        <p className="text-sm text-muted-foreground">Nothing scheduled yet.</p>
      )}

      {groups.map(
        (g) =>
          !!g.items.length && (
            <div key={g.title} className="space-y-2">
              <h3
                className={`text-xs font-semibold uppercase tracking-wide ${
                  g.title === "Overdue" ? "text-destructive" : "text-muted-foreground"
                }`}
              >
                {g.title}
              </h3>
              <ul className="space-y-2">
                {g.items.map((e) => (
                  <EntryCard
                    key={completionKey(e.subject_type, e.subject_id, e.rule_id, e.due_likely)}
                    entry={e}
                    done={false}
                    busy={busyKey === completionKey(e.subject_type, e.subject_id, e.rule_id, e.due_likely)}
                    onToggle={(d) => toggle(e, d)}
                  />
                ))}
              </ul>
            </div>
          )
      )}

      {!!doneItems.length && (
        <details className="space-y-2">
          <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Done ({doneItems.length})
          </summary>
          <ul className="mt-2 space-y-2">
            {doneItems.map((e) => (
              <EntryCard
                key={completionKey(e.subject_type, e.subject_id, e.rule_id, e.due_likely)}
                entry={e}
                done
                busy={busyKey === completionKey(e.subject_type, e.subject_id, e.rule_id, e.due_likely)}
                onToggle={(d) => toggle(e, d)}
              />
            ))}
          </ul>
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
