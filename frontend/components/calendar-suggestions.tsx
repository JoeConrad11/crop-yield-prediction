"use client";

import { useState } from "react";
import { Lightbulb } from "lucide-react";

import type { CalendarMissingAnchor, CalendarNote } from "@/lib/types";
import { anchorLabel } from "@/lib/calendar-labels";

// Smart next steps, derived from what the calendar could NOT schedule yet:
// a date it needs (asked for inline, one tap to add) or a field it can't
// project (no planting date). Every suggestion is the direct consequence of
// a cited rule needing an input -- the calendar never guesses a date to
// fill the gap. See src/farm_calendar.py missing_anchors().
export function CalendarSuggestions({
  missingAnchors,
  notes,
  hasAnything,
  onAddAnchor,
}: {
  missingAnchors: CalendarMissingAnchor[];
  notes: CalendarNote[];
  hasAnything: boolean;
  onAddAnchor: (m: CalendarMissingAnchor, date: string) => Promise<void>;
}) {
  const actionableNotes = notes.filter((n) => n.code === "needs_planting_date" || n.code === "no_knowledge");
  if (hasAnything && !missingAnchors.length && !actionableNotes.length) return null;

  return (
    <div className="space-y-2 rounded-xl border border-primary/30 bg-primary/5 p-3">
      <p className="flex items-center gap-1.5 text-sm font-medium text-foreground">
        <Lightbulb className="size-4 text-primary" aria-hidden="true" />
        Suggested next steps
      </p>
      {!hasAnything && (
        <p className="text-sm text-muted-foreground">
          Start by adding a field with its crop and planting date, or a group of livestock, below. The calendar fills
          in from there -- each item comes with its source.
        </p>
      )}
      {missingAnchors.map((m) => (
        <AnchorSuggestion key={`${m.subject_type}-${m.subject_id}-${m.anchor}`} missing={m} onAdd={onAddAnchor} />
      ))}
      {actionableNotes.map((n, i) => (
        <p key={`${n.code}-${n.subject_id}-${i}`} className="text-sm text-muted-foreground">
          {n.message}
        </p>
      ))}
    </div>
  );
}

function AnchorSuggestion({
  missing,
  onAdd,
}: {
  missing: CalendarMissingAnchor;
  onAdd: (m: CalendarMissingAnchor, date: string) => Promise<void>;
}) {
  const [date, setDate] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <span className="text-muted-foreground">
        When&apos;s the <span className="font-medium text-foreground">{anchorLabel(missing.anchor).toLowerCase()}</span>{" "}
        for {missing.subject_name ?? "this group"}?
      </span>
      <input
        type="date"
        value={date}
        onChange={(e) => setDate(e.target.value)}
        className="rounded-lg border border-border bg-background px-2 py-1 text-sm text-foreground outline-none focus:border-primary"
      />
      <button
        type="button"
        disabled={!date || busy}
        onClick={async () => {
          setBusy(true);
          try {
            await onAdd(missing, date);
          } finally {
            setBusy(false);
          }
        }}
        className="cursor-pointer rounded-lg bg-primary px-3 py-1 text-sm font-medium text-primary-foreground shadow-sm transition-opacity hover:opacity-90 disabled:opacity-50"
      >
        {busy ? "Adding..." : "Add"}
      </button>
    </div>
  );
}
