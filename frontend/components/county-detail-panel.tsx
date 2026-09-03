"use client";

import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";

import { fetchLatestPredictions } from "@/lib/api-client";

import { YieldTrendChart } from "./yield-trend-chart";

export function CountyDetailPanel({
  crop,
  stateFips,
  countyFips,
  countyName,
  onClose,
}: {
  crop: string;
  stateFips: string;
  countyFips: string;
  countyName: string;
  onClose: () => void;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["predictions", "latest", crop, stateFips, countyFips],
    queryFn: () => fetchLatestPredictions({ crop, state: stateFips, county: countyFips }),
  });
  const prediction = data?.[0];

  return (
    <div className="mb-4 rounded-xl border border-accent/40 bg-card p-4 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="font-heading text-base font-semibold text-card-foreground">{countyName}</h3>
          <p className="text-xs capitalize text-muted-foreground">{crop} yield trend</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close county detail"
          className="cursor-pointer rounded-full p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <X size={16} />
        </button>
      </div>

      {isLoading ? (
        <div className="mt-3 h-48 animate-pulse rounded-lg bg-muted" />
      ) : !prediction ? (
        <p className="mt-3 text-sm text-muted-foreground">No {crop} prediction for this county yet.</p>
      ) : (
        <div className="mt-2">
          <YieldTrendChart
            crop={crop}
            state={stateFips}
            county={countyFips}
            year={prediction.year}
            predictedYield={prediction.predicted_yield_bu_acre}
            predictedLow={prediction.predicted_yield_low}
            predictedHigh={prediction.predicted_yield_high}
          />
          {prediction.coverage_tier && (
            <p className="mt-1 text-center text-xs text-muted-foreground">
              Confidence: <span className="font-medium capitalize">{prediction.coverage_tier}</span> coverage
              {prediction.confidence_mae !== null
                ? ` (±${prediction.confidence_mae.toFixed(1)} bu/acre)`
                : ""}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
