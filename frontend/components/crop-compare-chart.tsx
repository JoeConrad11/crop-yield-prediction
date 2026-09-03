"use client";

import { useQueries, useQuery } from "@tanstack/react-query";
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

import { fetchCrops, fetchYieldHistory } from "@/lib/api-client";

// Cycles through the theme's chart tokens -- generic over however many
// crops GET /crops returns, not hardcoded to corn+soybean.
const LINE_COLORS = [
  "var(--color-chart-1)",
  "var(--color-chart-2)",
  "var(--color-chart-3)",
  "var(--color-chart-4)",
  "var(--color-chart-5)",
];

export function CropCompareChart({ state, county }: { state: string; county: string }) {
  const cropsQuery = useQuery({ queryKey: ["crops"], queryFn: fetchCrops, staleTime: Infinity });
  const crops = cropsQuery.data ?? [];

  const historyQueries = useQueries({
    queries: crops.map((c) => ({
      queryKey: ["history", c.id, state, county],
      queryFn: () => fetchYieldHistory({ crop: c.id, state, county }),
    })),
  });

  if (cropsQuery.isLoading || historyQueries.some((q) => q.isLoading)) {
    return <div className="h-64 w-full animate-pulse rounded-lg bg-muted" />;
  }

  if (cropsQuery.isError || historyQueries.some((q) => q.isError)) {
    return <p className="text-sm text-destructive">Couldn&apos;t load crop comparison.</p>;
  }

  // Corn and soybean yields are different units of "success" (bu/acre means
  // something different for each crop) -- plotting raw values on one axis
  // would just show corn dwarfing soybeans, not which crop trends up/down.
  // Index each crop to its own county average (=100) so the chart compares
  // *trend*, not magnitude.
  const rows = new Map<number, Record<string, number>>();
  crops.forEach((c, i) => {
    const hist = historyQueries[i].data ?? [];
    if (hist.length === 0) return;
    const mean = hist.reduce((sum, h) => sum + h.yield_bu_acre, 0) / hist.length;
    for (const h of hist) {
      const row = rows.get(h.year) ?? { year: h.year };
      row[c.display_name] = (h.yield_bu_acre / mean) * 100;
      rows.set(h.year, row);
    }
  });
  const data = [...rows.values()].sort((a, b) => a.year - b.year);

  return (
    <div>
      <ResponsiveContainer width="100%" height={260}>
        <ComposedChart data={data} margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
          <XAxis dataKey="year" tick={{ fontSize: 12, fill: "var(--color-muted-foreground)" }} />
          <YAxis
            tick={{ fontSize: 12, fill: "var(--color-muted-foreground)" }}
            width={44}
            label={{ value: "% of avg", angle: -90, position: "insideLeft", fontSize: 11, fill: "var(--color-muted-foreground)" }}
          />
          <Tooltip
            contentStyle={{
              background: "var(--color-card)",
              border: "1px solid var(--color-border)",
              borderRadius: 8,
              fontSize: 12,
            }}
            formatter={(value) => `${Number(value).toFixed(0)}% of county average`}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {crops.map((c, i) => (
            <Line
              key={c.id}
              type="monotone"
              dataKey={c.display_name}
              stroke={LINE_COLORS[i % LINE_COLORS.length]}
              strokeWidth={2}
              dot={{ r: 3 }}
              connectNulls
            />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
      <p className="mt-1 text-center text-xs text-muted-foreground">
        Each crop indexed to its own county average (=100%) -- corn and soybean
        bu/acre aren&apos;t comparable in raw terms, this compares trend, not size.
      </p>
    </div>
  );
}
