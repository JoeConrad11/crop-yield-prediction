"use client";

import { useQuery } from "@tanstack/react-query";
import { Maximize2, X } from "lucide-react";
import { useState } from "react";

import { fetchLatestPredictions } from "@/lib/api-client";

import { CountyTrendDialog } from "./county-trend-dialog";
import { YieldTrendChart } from "./yield-trend-chart";

type DialogTab = "season" | "why" | "accuracy" | "compare";

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
  const [dialogTab, setDialogTab] = useState<DialogTab | null>(null);
  const { data, isLoading } = useQuery({
    queryKey: ["predictions", "latest", crop, stateFips, countyFips],
    queryFn: () => fetchLatestPredictions({ crop, state: stateFips, county: countyFips }),
  });
  const prediction = data?.[0];

  function openDialog(tab: DialogTab) {
    setDialogTab(tab);
  }

  return (
    <div className="mb-4 rounded-xl border border-accent/40 bg-card p-4 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="font-heading text-base font-semibold text-card-foreground">{countyName}</h3>
          <p className="text-xs capitalize text-muted-foreground">{crop} yield trend</p>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => openDialog("season")}
            aria-label="Open full trend view"
            title="Dive deeper"
            className="cursor-pointer rounded-full p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <Maximize2 size={14} />
          </button>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close county detail"
            className="cursor-pointer rounded-full p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="mt-3 h-48 animate-pulse rounded-lg bg-muted" />
      ) : !prediction ? (
        <p className="mt-3 text-sm text-muted-foreground">No {crop} prediction for this county yet.</p>
      ) : (
        <div className="mt-2">
          <button
            type="button"
            onClick={() => openDialog("why")}
            className="mb-2 flex w-full cursor-pointer items-baseline justify-between rounded-lg bg-muted px-3 py-2 text-left transition-colors hover:bg-secondary/15"
          >
            <span>
              <span className="text-2xl font-semibold tabular-nums text-foreground">
                {prediction.predicted_yield_bu_acre.toFixed(0)}
              </span>
              <span className="ml-1 text-xs text-muted-foreground">bu/acre predicted</span>
            </span>
            <span className="text-xs font-medium text-secondary">Why? &rarr;</span>
          </button>

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
          <button
            type="button"
            onClick={() => openDialog("season")}
            className="mt-2 w-full cursor-pointer rounded-lg border border-border py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            Dive deeper into the data
          </button>
        </div>
      )}

      <CountyTrendDialog
        crop={crop}
        stateFips={stateFips}
        countyFips={countyFips}
        countyName={countyName}
        open={dialogTab !== null}
        onOpenChange={(open) => setDialogTab(open ? (dialogTab ?? "season") : null)}
        defaultTab={dialogTab ?? "season"}
      />
    </div>
  );
}
