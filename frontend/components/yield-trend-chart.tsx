"use client";

import { useQuery } from "@tanstack/react-query";
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { fetchYieldHistory } from "@/lib/api-client";

// "Line with Confidence Band" pattern: solid line for actual history, a
// dashed segment connecting the last actual year to this year's prediction,
// and a shaded vertical band showing the prediction's low/high range --
// never color alone (solid vs. dashed carries the actual/forecast meaning).
export function YieldTrendChart({
  crop,
  state,
  county,
  year,
  predictedYield,
  predictedLow,
  predictedHigh,
}: {
  crop: string;
  state: string;
  county: string;
  year: number;
  predictedYield: number;
  predictedLow: number | null;
  predictedHigh: number | null;
}) {
  const { data: history, isLoading, isError } = useQuery({
    queryKey: ["history", crop, state, county],
    queryFn: () => fetchYieldHistory({ crop, state, county }),
  });

  if (isLoading) {
    return <div className="h-48 w-full animate-pulse rounded-lg bg-muted" />;
  }

  if (isError || !history) {
    return <p className="text-sm text-destructive">Couldn&apos;t load yield history.</p>;
  }

  type Row = { year: number; actual?: number; forecast?: number };
  const rows: Row[] = history.map((h) => ({ year: h.year, actual: h.yield_bu_acre }));

  if (rows.length > 0) {
    rows[rows.length - 1] = { ...rows[rows.length - 1], forecast: rows[rows.length - 1].actual };
  }
  rows.push({ year, forecast: predictedYield });

  const hasBand = predictedLow !== null && predictedHigh !== null;

  return (
    <div>
      <ResponsiveContainer width="100%" height={200}>
        <ComposedChart data={rows} margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
          <XAxis dataKey="year" tick={{ fontSize: 12, fill: "var(--color-muted-foreground)" }} />
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
            formatter={(value, name) => [
              `${Number(value).toFixed(1)} bu/acre`,
              name === "actual" ? "Actual" : "Predicted",
            ]}
          />
          {hasBand && (
            <ReferenceArea
              x1={year}
              x2={year}
              y1={predictedLow!}
              y2={predictedHigh!}
              fill="var(--color-accent)"
              fillOpacity={0.18}
              stroke="var(--color-accent)"
              strokeOpacity={0.4}
            />
          )}
          <Line
            type="monotone"
            dataKey="actual"
            stroke="var(--color-primary)"
            strokeWidth={2}
            dot={{ r: 3 }}
            connectNulls={false}
            name="actual"
          />
          <Line
            type="monotone"
            dataKey="forecast"
            stroke="var(--color-accent)"
            strokeWidth={2}
            strokeDasharray="6 4"
            dot={{ r: 3 }}
            connectNulls={false}
            name="forecast"
          />
        </ComposedChart>
      </ResponsiveContainer>
      <p className="mt-1 text-center text-xs text-muted-foreground">
        Solid = actual yield &middot; dashed = this season&apos;s prediction
        {hasBand ? " (shaded band = confidence range)" : ""}
      </p>
    </div>
  );
}
