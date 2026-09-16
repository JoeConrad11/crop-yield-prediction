"use client";

import { useQuery } from "@tanstack/react-query";
import { Sprout } from "lucide-react";

import { fetchFieldStage } from "@/lib/api-client";
import type { Field } from "@/lib/farm-types";

// Agronomy Layer 1 (see ../../ARCHITECTURE.md). Shown for EVERY field with
// a crop and planting date, regardless of size -- growth stage comes from
// 4km temperature data, so unlike the yield prediction it has no
// small-field resolution limit. For a farmer whose field is too small for
// a yield number, this is the part of the product that still works, so it
// deliberately renders on its own rather than inside the prediction panel.
export function FieldStage({ field, crop }: { field: Field; crop: string }) {
  const enabled = !!crop && !!field.planting_date;

  const { data, isLoading, isError } = useQuery({
    queryKey: ["field-stage", field.id, crop, field.planting_date],
    queryFn: () =>
      fetchFieldStage({
        boundary: field.boundary,
        crop,
        plantingDate: field.planting_date,
        fieldId: String(field.id),
      }),
    enabled,
    retry: false,
    staleTime: 1000 * 60 * 60 * 6, // heat accumulates slowly; don't refetch on every render
  });

  // Silent when we can't say anything: no crop/date yet is the normal
  // starting state, not an error worth showing, and the inputs that fix it
  // are right there in the same card.
  if (!enabled || isError || isLoading || !data) return null;

  const stage = data.stage;
  const next = data.next_stage;

  return (
    <div className="mt-2 flex gap-2 rounded-lg border border-primary/30 bg-primary/5 px-2.5 py-2">
      <Sprout className="mt-0.5 size-3.5 shrink-0 text-primary" aria-hidden="true" />
      <div className="text-xs">
        <p className="font-medium text-card-foreground">
          {stage ? `${stage.code} -- ${stage.description}` : "Planted, not yet emerged"}
        </p>
        <p className="mt-0.5 text-muted-foreground">
          {data.days_since_planting} days since planting -- {Math.round(data.accumulated_gdd)} growing
          degree units
          {next && data.next_stage_gdd_away != null && (
            <> -- {next.code} ({next.description}) is ~{Math.round(data.next_stage_gdd_away)} GDU away</>
          )}
        </p>
        {/* The caveat travels with the number, per ARCHITECTURE.md's rule
            that agronomic claims carry their sourcing and limits. */}
        <p className="mt-1 text-[11px] text-muted-foreground/80">{data.caveat}</p>
      </div>
    </div>
  );
}
