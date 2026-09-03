"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchLatestPredictions } from "@/lib/api-client";

import { CropCompareChart } from "./crop-compare-chart";
import { ModelAccuracyChart } from "./model-accuracy-chart";
import { PredictionExplainChart } from "./prediction-explain-chart";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "./ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";
import { YieldTrendChart } from "./yield-trend-chart";

export function CountyTrendDialog({
  crop,
  stateFips,
  countyFips,
  countyName,
  open,
  onOpenChange,
  defaultTab = "season",
}: {
  crop: string;
  stateFips: string;
  countyFips: string;
  countyName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultTab?: "season" | "why" | "accuracy" | "compare";
}) {
  const { data } = useQuery({
    queryKey: ["predictions", "latest", crop, stateFips, countyFips],
    queryFn: () => fetchLatestPredictions({ crop, state: stateFips, county: countyFips }),
    enabled: open,
  });
  const prediction = data?.[0];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{countyName}</DialogTitle>
        </DialogHeader>

        <Tabs defaultValue={defaultTab}>
          <TabsList>
            <TabsTrigger value="season">This season</TabsTrigger>
            <TabsTrigger value="why">Why this prediction</TabsTrigger>
            <TabsTrigger value="accuracy">Model accuracy</TabsTrigger>
            <TabsTrigger value="compare">Compare crops</TabsTrigger>
          </TabsList>

          <TabsContent value="season" className="pt-4">
            {prediction ? (
              <>
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
              </>
            ) : (
              <p className="text-sm text-muted-foreground">No {crop} prediction for this county yet.</p>
            )}
          </TabsContent>

          <TabsContent value="why" className="pt-4">
            <PredictionExplainChart crop={crop} state={stateFips} county={countyFips} />
          </TabsContent>

          <TabsContent value="accuracy" className="pt-4">
            <ModelAccuracyChart crop={crop} state={stateFips} county={countyFips} />
          </TabsContent>

          <TabsContent value="compare" className="pt-4">
            <CropCompareChart state={stateFips} county={countyFips} />
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
