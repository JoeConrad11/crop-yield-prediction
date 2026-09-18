"use client";

import { useState } from "react";
import { PawPrint, Trash2, X } from "lucide-react";

import { addFarmEvent, createHerd, deleteFarmEvent, deleteHerd } from "@/lib/farm-client";
import type { FarmEvent, Herd } from "@/lib/farm-types";
import type { CalendarKnowledge } from "@/lib/types";
import { anchorLabel, formatDay, speciesLabel } from "@/lib/calendar-labels";

const inputClass =
  "rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-primary";

// Livestock groups and the anchor dates their schedules hang off. Species
// and the dates worth entering come from GET /calendar/knowledge, so a new
// species with cited rules shows up here with no frontend change.
export function LivestockPanel({
  farmId,
  herds,
  events,
  knowledge,
  onChanged,
}: {
  farmId: number;
  herds: Herd[];
  events: FarmEvent[];
  knowledge: CalendarKnowledge;
  onChanged: () => Promise<void> | void;
}) {
  const speciesOptions = Object.entries(knowledge)
    .filter(([, v]) => v.anchors.length > 0)
    .map(([kind]) => kind);

  const [adding, setAdding] = useState(false);
  const [species, setSpecies] = useState("");
  const [name, setName] = useState("");
  const [headCount, setHeadCount] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await action();
      await onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : (e as { message?: string })?.message ?? "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  async function handleAddHerd() {
    await run(async () => {
      await createHerd({
        farmId,
        species,
        name: name.trim(),
        headCount: headCount ? Number(headCount) : null,
      });
      setAdding(false);
      setSpecies("");
      setName("");
      setHeadCount("");
    });
  }

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="font-heading text-lg font-semibold text-foreground">Your livestock</h2>
        {!adding && !!speciesOptions.length && (
          <button
            type="button"
            onClick={() => setAdding(true)}
            className="cursor-pointer rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground shadow-sm transition-opacity hover:opacity-90"
          >
            Add livestock
          </button>
        )}
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {!herds.length && !adding && (
        <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-accent/40 p-6 text-center">
          <PawPrint className="size-6 text-accent" aria-hidden="true" />
          <p className="text-sm text-muted-foreground">
            Add cattle or sheep and the calendar will show what&apos;s due and when, with a source for each item.
          </p>
        </div>
      )}

      {herds.map((herd) => (
        <HerdCard
          key={herd.id}
          herd={herd}
          anchors={knowledge[herd.species]?.anchors ?? []}
          events={events.filter((e) => e.subject_type === "herd" && e.subject_id === herd.id)}
          busy={busy}
          onDelete={() => run(() => deleteHerd(farmId, herd.id))}
          onAddDate={(kind, date) =>
            run(() => addFarmEvent({ farmId, subjectType: "herd", subjectId: herd.id, kind, eventDate: date }))
          }
          onDeleteDate={(eventId) => run(() => deleteFarmEvent(eventId))}
        />
      ))}

      {adding && (
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-accent/40 bg-card p-4 shadow-sm">
          <select value={species} onChange={(e) => setSpecies(e.target.value)} className={`${inputClass} cursor-pointer`}>
            <option value="" disabled>
              Which animals?
            </option>
            {speciesOptions.map((s) => (
              <option key={s} value={s}>
                {speciesLabel(s)}
              </option>
            ))}
          </select>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Group name (e.g. Spring ewes)"
            className={`${inputClass} min-w-48 flex-1`}
          />
          <input
            type="number"
            min={0}
            value={headCount}
            onChange={(e) => setHeadCount(e.target.value)}
            placeholder="Head (optional)"
            className={`${inputClass} w-36`}
          />
          <div className="ml-auto flex gap-2">
            <button
              type="button"
              onClick={() => setAdding(false)}
              className="cursor-pointer rounded-lg border border-border px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleAddHerd}
              disabled={!species || !name.trim() || busy}
              className="cursor-pointer rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground shadow-sm transition-opacity hover:opacity-90 disabled:opacity-50"
            >
              {busy ? "Saving..." : "Save"}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

function HerdCard({
  herd,
  anchors,
  events,
  busy,
  onDelete,
  onAddDate,
  onDeleteDate,
}: {
  herd: Herd;
  anchors: string[];
  events: FarmEvent[];
  busy: boolean;
  onDelete: () => void;
  onAddDate: (kind: string, date: string) => void;
  onDeleteDate: (eventId: number) => void;
}) {
  const [kind, setKind] = useState("");
  const [date, setDate] = useState("");

  return (
    <div className="rounded-xl border border-accent/40 bg-card px-4 py-3 shadow-sm">
      <div className="flex items-center justify-between">
        <div>
          <p className="font-medium text-card-foreground">{herd.name}</p>
          <p className="text-xs text-muted-foreground">
            {speciesLabel(herd.species)}
            {herd.head_count != null ? ` · ${herd.head_count} head` : ""}
          </p>
        </div>
        <button
          type="button"
          onClick={onDelete}
          disabled={busy}
          aria-label={`Delete ${herd.name}`}
          className="cursor-pointer rounded-full p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-destructive"
        >
          <Trash2 className="size-4" aria-hidden="true" />
        </button>
      </div>

      {!!events.length && (
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {events.map((e) => (
            <li
              key={e.id}
              className="flex items-center gap-1 rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground"
            >
              {anchorLabel(e.kind)}: {formatDay(e.event_date, true)}
              <button
                type="button"
                onClick={() => onDeleteDate(e.id)}
                aria-label={`Remove ${anchorLabel(e.kind)}`}
                className="cursor-pointer rounded-full p-0.5 hover:text-destructive"
              >
                <X className="size-3" aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <select value={kind} onChange={(e) => setKind(e.target.value)} className={`${inputClass} cursor-pointer py-1.5`}>
          <option value="" disabled>
            Add a date...
          </option>
          {anchors.map((a) => (
            <option key={a} value={a}>
              {anchorLabel(a)}
            </option>
          ))}
        </select>
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className={`${inputClass} py-1.5`} />
        <button
          type="button"
          disabled={!kind || !date || busy}
          onClick={() => {
            onAddDate(kind, date);
            setKind("");
            setDate("");
          }}
          className="cursor-pointer rounded-lg border border-border px-3 py-1.5 text-sm text-foreground transition-colors hover:bg-muted disabled:opacity-50"
        >
          Add
        </button>
      </div>
    </div>
  );
}
