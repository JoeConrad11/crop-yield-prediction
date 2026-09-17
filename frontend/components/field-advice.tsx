"use client";

import { useQuery } from "@tanstack/react-query";
import { BookOpen, Lightbulb } from "lucide-react";

import { fetchFieldAdvice } from "@/lib/api-client";
import type { Field } from "@/lib/farm-types";

// Layer 3 (see ../../ARCHITECTURE.md, "Layer 3 -- Advice, sourced not
// invented"). Auto-fetches like FieldStage, since half of what it shows
// (sourced notes) needs only crop + planting date, not a successful yield
// prediction -- and the other half (SHAP) degrades gracefully to nothing
// shown when the yield path has nothing to explain yet, rather than an
// error, since that's the normal state for most fields most of the season.
export function FieldAdvice({ field, crop }: { field: Field; crop: string }) {
  const enabled = !!crop;

  const { data, isLoading, isError } = useQuery({
    queryKey: ["field-advice", field.id, crop, field.planting_date],
    queryFn: () =>
      fetchFieldAdvice({
        boundary: field.boundary,
        crop,
        plantingDate: field.planting_date,
        fieldId: String(field.id),
      }),
    enabled,
    retry: false,
    staleTime: 1000 * 60 * 60 * 6,
  });

  if (!enabled || isError || isLoading || !data) return null;

  const shap = data.shap_explanation;
  const notes = data.sourced_notes;
  if (!shap && notes.length === 0) return null;

  return (
    <div className="mt-2 space-y-1.5">
      {shap && (
        <div className="flex gap-2 rounded-lg border border-border bg-muted/30 px-2.5 py-2">
          <Lightbulb className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
          <div className="text-xs">
            <p className="font-medium text-card-foreground">Why this number</p>
            <ul className="mt-1 space-y-0.5">
              {shap.top_contributions.slice(0, 3).map((c) => (
                <li key={c.feature} className="text-muted-foreground">
                  {c.label}: {c.shap_value_bu_acre >= 0 ? "+" : ""}
                  {c.shap_value_bu_acre.toFixed(1)} bu/acre
                </li>
              ))}
            </ul>
            <p className="mt-1 text-[11px] text-muted-foreground/80">
              Reads your field&apos;s own satellite data against the model&apos;s trained patterns, not a
              guess -- the biggest movers are shown above, from a total of{" "}
              {shap.top_contributions.length + shap.other_feature_count} factors.
            </p>
          </div>
        </div>
      )}

      {notes.map((note) => (
        <div key={note.id} className="flex gap-2 rounded-lg border border-border bg-muted/30 px-2.5 py-2">
          <BookOpen className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
          <div className="text-xs">
            <p className="text-card-foreground">{note.text}</p>
            <a
              href={note.source_url}
              target="_blank"
              rel="noreferrer"
              className="mt-1 inline-block text-[11px] text-muted-foreground/80 underline decoration-dotted hover:text-muted-foreground"
            >
              Source: {note.source_name}
            </a>
          </div>
        </div>
      ))}
    </div>
  );
}
