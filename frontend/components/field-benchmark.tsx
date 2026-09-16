"use client";

import { useState } from "react";
import { Loader2, TrendingUp } from "lucide-react";

import { fetchFieldBenchmark, FieldPredictionError } from "@/lib/api-client";
import type { Field } from "@/lib/farm-types";
import type { FieldStageBenchmark } from "@/lib/types";

// The small-farm monitoring product (see ../../ARCHITECTURE.md). Compares
// this field's canopy to ITSELF in prior seasons at the same GROWTH STAGE.
//
// Why this matters more than it looks: it never leaves Sentinel-2 -- same
// sensor, same polygon, same masking -- so the cross-sensor calibration
// problem that makes the yield model unusable on small fields simply
// doesn't arise. A farmer whose field is too small for a yield number can
// still be told, reliably, that this season is running behind its own norm.
export function FieldBenchmark({ field, crop }: { field: Field; crop: string }) {
  const [status, setStatus] = useState<"idle" | "loading" | "error" | "done">("idle");
  const [data, setData] = useState<FieldStageBenchmark | null>(null);
  const [error, setError] = useState("");

  if (!crop || !field.planting_date) return null;

  async function run() {
    setStatus("loading");
    setError("");
    try {
      setData(
        await fetchFieldBenchmark({
          boundary: field.boundary,
          crop,
          plantingDate: field.planting_date,
          fieldId: String(field.id),
        })
      );
      setStatus("done");
    } catch (err) {
      setError(err instanceof FieldPredictionError ? err.message : "Something went wrong.");
      setStatus("error");
    }
  }

  const pct = data?.pct_vs_history;
  const sd = data?.sd_from_history;
  // Only call a season unusual when it's genuinely outside the field's own
  // year-to-year spread -- otherwise this is just noise dressed as insight.
  const notable = sd != null && Math.abs(sd) >= 2;

  return (
    <div className="mt-2">
      {status !== "done" && (
        <button
          type="button"
          onClick={run}
          disabled={status === "loading"}
          className="flex cursor-pointer items-center gap-1.5 rounded-lg border border-border px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted disabled:opacity-50"
        >
          {status === "loading" ? (
            <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
          ) : (
            <TrendingUp className="size-3.5" aria-hidden="true" />
          )}
          {status === "loading" ? "Comparing seasons (~20s)..." : "Compare to past seasons"}
        </button>
      )}

      {status === "error" && (
        <p className="mt-1.5 rounded-lg border border-destructive/40 bg-destructive/5 px-2.5 py-1.5 text-xs text-destructive">
          {error}
        </p>
      )}

      {status === "done" && data && (
        <div className="rounded-lg border border-border bg-muted/30 px-3 py-2">
          {data.current_ndvi == null || pct == null ? (
            <p className="text-xs text-muted-foreground">{data.message}</p>
          ) : (
            <>
              <p className="text-sm font-medium text-card-foreground">
                {Math.abs(pct) < 3
                  ? "Right about normal for this field"
                  : `${pct > 0 ? "Ahead of" : "Behind"} this field's own history by ${Math.abs(pct).toFixed(0)}%`}
                {notable && (
                  <span className={pct > 0 ? "text-primary" : "text-destructive"}>
                    {" "}-- {Math.abs(sd!).toFixed(1)} sd, unusual for this field
                  </span>
                )}
              </p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Canopy {data.current_ndvi.toFixed(3)} vs {data.history_mean_ndvi?.toFixed(3)} average at
                the same stage{data.stage ? ` (${data.stage.code})` : ""} in past seasons
              </p>
              <ul className="mt-1.5 space-y-0.5">
                {data.history.map((h) => (
                  <li key={h.year} className="text-[11px] text-muted-foreground/80">
                    {h.year}:{" "}
                    {h.ndvi == null
                      ? (h.note ?? "no clear imagery")
                      : `${h.ndvi.toFixed(3)} on ${h.equivalent_date}`}
                  </li>
                ))}
              </ul>
              {/* The method and its assumption travel with the number. */}
              <p className="mt-1.5 text-[11px] text-muted-foreground/70">
                Compared at equal accumulated heat, not equal calendar date.{" "}
                {data.planting_assumption.charAt(0).toUpperCase() + data.planting_assumption.slice(1)}.
              </p>
            </>
          )}
        </div>
      )}
    </div>
  );
}
