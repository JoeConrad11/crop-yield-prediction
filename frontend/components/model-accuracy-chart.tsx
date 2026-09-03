"use client";

import { useQuery } from "@tanstack/react-query";
import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { fetchBacktestPredictions } from "@/lib/api-client";

// True held-out (leave-one-year-out) predictions across the full training
// window -- see src/backtest_recent_years.py. Not the production model's
// in-sample fit. Same solid-actual/dashed-predicted convention as the
// "This season" tab, so the two read as one visual language.
export function ModelAccuracyChart({
  crop,
  state,
  county,
}: {
  crop: string;
  state: string;
  county: string;
}) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["backtest", crop, state, county],
    queryFn: () => fetchBacktestPredictions({ crop, state, county }),
  });

  if (isLoading) {
    return <div className="h-64 w-full animate-pulse rounded-lg bg-muted" />;
  }

  if (isError || !data) {
    return <p className="text-sm text-destructive">Couldn&apos;t load model accuracy data.</p>;
  }

  if (data.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No held-out backtest for this county yet -- it may have been below the
        crop-pixel-coverage threshold in 2024 or 2025.
      </p>
    );
  }

  const rows = [...data]
    .sort((a, b) => a.year - b.year)
    .map((d) => ({ year: d.year, Actual: d.actual_yield_bu_acre, Predicted: d.predicted_yield_bu_acre }));

  return (
    <div>
      <ResponsiveContainer width="100%" height={260}>
        <ComposedChart data={rows} margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
          <XAxis
            dataKey="year"
            type="category"
            allowDuplicatedCategory={false}
            tick={{ fontSize: 12, fill: "var(--color-muted-foreground)" }}
          />
          <YAxis
            tick={{ fontSize: 12, fill: "var(--color-muted-foreground)" }}
            width={40}
            label={{ value: "bu/acre", angle: -90, position: "insideLeft", fontSize: 11, fill: "var(--color-muted-foreground)" }}
          />
          <Tooltip
            contentStyle={{
              background: "var(--color-card)",
              border: "1px solid var(--color-border)",
              borderRadius: 8,
              fontSize: 12,
            }}
            formatter={(value) => `${Number(value).toFixed(1)} bu/acre`}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line
            type="monotone"
            dataKey="Actual"
            stroke="var(--color-primary)"
            strokeWidth={2}
            dot={{ r: 4 }}
          />
          <Line
            type="monotone"
            dataKey="Predicted"
            stroke="var(--color-secondary)"
            strokeWidth={2}
            strokeDasharray="6 4"
            dot={{ r: 4 }}
          />
        </ComposedChart>
      </ResponsiveContainer>
      <p className="mt-1 text-center text-xs text-muted-foreground">
        Solid = actual yield &middot; dashed = held-out prediction (the model
        never saw this county-year while training).
      </p>
    </div>
  );
}
