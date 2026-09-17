"use client";

import { useState } from "react";
import { Info, Loader2, Sparkles } from "lucide-react";

import { predictField, FieldPredictionError } from "@/lib/api-client";
import type { Field } from "@/lib/farm-types";
import type { CropMeta, FieldPrediction as FieldPredictionResult } from "@/lib/types";
import { FieldStage } from "./field-stage";
import { FieldBenchmark } from "./field-benchmark";
import { FieldAdvice } from "./field-advice";

// Phase 3 of the farmer-app roadmap (see ../../ARCHITECTURE.md): apply the
// county-calibrated model to THIS field's own satellite data instead of
// showing the farmer their county's average. Deliberately framed as "vs.
// your county" everywhere below, not a bare bushels/acre number -- there's
// no field-level yield ground truth to train a field-specific model on
// (see src/predict_field.py's docstring), so honesty about what this is
// (and isn't) matters more here than anywhere else in the app.
export function FieldPredictionPanel({
  field,
  crops,
  onSeasonChange,
}: {
  field: Field;
  crops: CropMeta[];
  onSeasonChange?: (params: { primaryCrop?: string; plantingDate?: string }) => void;
}) {
  // Empty until the farmer actually says -- deliberately NOT defaulted to
  // the first crop. The entire point of this field is that it's *confirmed*
  // by the farmer; silently persisting a default would record a guess as an
  // answer, which is the CDL-guessing problem 4b exists to remove, just
  // moved into our own database (see ARCHITECTURE.md Phase 4b).
  const [crop, setCrop] = useState(field.primary_crop ?? "");
  const [plantingDate, setPlantingDate] = useState(field.planting_date ?? "");
  const [status, setStatus] = useState<"idle" | "loading" | "error" | "done">("idle");
  const [result, setResult] = useState<FieldPredictionResult | null>(null);
  const [error, setError] = useState("");
  // A "limitation" is the pipeline working correctly and honestly reporting
  // that it can't speak to this field this season -- most often because the
  // field is smaller than the satellite can resolve. Styled as information,
  // not as a failure: for the small farms this product targets, that state
  // is common, is not the farmer's fault, and is something we're actively
  // fixing (see ARCHITECTURE.md Phase 4a).
  const [isLimitation, setIsLimitation] = useState(false);

  async function handlePredict() {
    if (!crop) return;
    setStatus("loading");
    setError("");
    try {
      const prediction = await predictField({ boundary: field.boundary, crop, fieldId: String(field.id) });
      setResult(prediction);
      setStatus("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
      setIsLimitation(err instanceof FieldPredictionError && err.isLimitation);
      setStatus("error");
    }
  }

  // Crop and planting date are the farmer's own answer, so persist them
  // rather than re-asking every visit -- they're also what removes the
  // CDL-derived guessing from the pipeline (Phase 4b, see ARCHITECTURE.md).
  function handleCropChange(next: string) {
    setCrop(next);
    setResult(null);
    setStatus("idle");
    onSeasonChange?.({ primaryCrop: next });
  }

  function handlePlantingDateChange(next: string) {
    setPlantingDate(next);
    onSeasonChange?.({ plantingDate: next });
  }

  return (
    <div className="mt-2 space-y-2 border-t border-border/60 pt-2">
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={crop}
          onChange={(e) => handleCropChange(e.target.value)}
          className="cursor-pointer rounded-lg border border-border bg-background px-2 py-1 text-xs text-foreground outline-none focus:border-primary"
        >
          <option value="" disabled>
            Which crop?
          </option>
          {crops.map((c) => (
            <option key={c.id} value={c.id}>
              {c.display_name}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          Planted
          {/* Bounded because a segmented date input will emit a 6-digit
              year if you type into the wrong segment -- '122026-05-12'
              reached the database that way during testing. */}
          <input
            type="date"
            value={plantingDate}
            min={`${new Date().getFullYear() - 2}-01-01`}
            max={`${new Date().getFullYear() + 1}-12-31`}
            onChange={(e) => handlePlantingDateChange(e.target.value)}
            className="cursor-pointer rounded-lg border border-border bg-background px-1.5 py-1 text-xs text-foreground outline-none focus:border-primary"
          />
        </label>
        <button
          type="button"
          onClick={handlePredict}
          disabled={status === "loading" || !crop}
          className="flex cursor-pointer items-center gap-1.5 rounded-lg bg-accent px-2.5 py-1 text-xs font-medium text-accent-foreground shadow-sm transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {status === "loading" ? (
            <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
          ) : (
            <Sparkles className="size-3.5" aria-hidden="true" />
          )}
          {status === "loading" ? "Predicting..." : "Predict my field"}
        </button>
      </div>

      {/* Rendered above the prediction result and outside its status
          branches on purpose: growth stage is available at any field size,
          so it must still show when the yield prediction declines. */}
      <FieldStage field={field} crop={crop} />
      <FieldBenchmark field={field} crop={crop} />

      {status === "error" &&
        (isLimitation ? (
          <div className="flex gap-2 rounded-lg border border-accent/40 bg-accent/5 px-2.5 py-2">
            <Info className="mt-0.5 size-3.5 shrink-0 text-accent" aria-hidden="true" />
            <div className="text-xs text-muted-foreground">
              <p>{error}</p>
              <p className="mt-1 text-muted-foreground/80">
                Nothing&apos;s wrong with your field or your account -- today&apos;s imagery is 250m per
                pixel, which is coarser than a field this size. Higher-resolution imagery is in progress.
              </p>
            </div>
          </div>
        ) : (
          <p className="rounded-lg border border-destructive/40 bg-destructive/5 px-2.5 py-1.5 text-xs text-destructive">
            {error}
          </p>
        ))}

      {status === "done" && result && (
        <div className="rounded-lg border border-accent/40 bg-accent/5 px-3 py-2">
          <p className="text-sm font-semibold text-card-foreground">
            {result.predicted_yield_bu_acre.toFixed(1)} bu/acre
            {result.predicted_yield_low != null && result.predicted_yield_high != null && (
              <span className="ml-1.5 text-xs font-normal text-muted-foreground">
                (typically {result.predicted_yield_low.toFixed(0)}-{result.predicted_yield_high.toFixed(0)})
              </span>
            )}
          </p>
          {result.pct_vs_historical != null && (
            <p className="text-xs text-muted-foreground">
              {result.pct_vs_historical >= 0 ? "+" : ""}
              {result.pct_vs_historical.toFixed(1)}% vs. {result.county_name} County&apos;s historical average
            </p>
          )}
          <p className="mt-1 text-[11px] text-muted-foreground/80">
            Coverage: {result.coverage_tier}
            {result.crop_observed_acres != null &&
              ` (~${result.crop_observed_acres.toFixed(0)} acres of ${crop} detected)`}
            {" -- "}this reads your field&apos;s own satellite data through your county&apos;s trained model,
            not a field-specific one.
          </p>
        </div>
      )}

      {/* Layer 3 (see ../../ARCHITECTURE.md): pairs the number above with why
          it came out that way. Rendered outside the status branches, same
          reasoning as FieldStage -- its sourced-note half doesn't need a
          successful prediction, only crop + planting date. */}
      <FieldAdvice field={field} crop={crop} />
    </div>
  );
}
