"use client";

import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { fetchExplanation } from "@/lib/api-client";

const currency = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });

function fmtBu(n: number): string {
  return `${n >= 0 ? "+" : ""}${currency.format(n)} bu/acre`;
}

// Real per-instance SHAP values against the exact feature row
// predict_live.py used for this county (see api/routers/explain.py) -- not
// global feature importance. Green bars raised the prediction, gold bars
// lowered it, matching the map's own yield-gradient color meaning.
export function PredictionExplainChart({
  crop,
  state,
  county,
}: {
  crop: string;
  state: string;
  county: string;
}) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["explain", crop, state, county],
    queryFn: () => fetchExplanation({ crop, state, county }),
  });

  if (isLoading) {
    return <div className="h-72 w-full animate-pulse rounded-lg bg-muted" />;
  }

  if (isError || !data) {
    return (
      <p className="text-sm text-destructive">
        Couldn&apos;t load an explanation for this county yet.
      </p>
    );
  }

  const rows = data.top_contributions.map((c) => ({
    name: c.label,
    value: c.shap_value_bu_acre,
  }));

  return (
    <div>
      <div className="mb-3 grid grid-cols-2 gap-2 text-xs">
        <div className="rounded-lg bg-muted px-2.5 py-1.5">
          <div className="text-muted-foreground">Model baseline</div>
          <div className="font-medium tabular-nums text-foreground">{fmtBu(data.base_value_bu_acre)}</div>
        </div>
        <div className="rounded-lg bg-muted px-2.5 py-1.5">
          <div className="text-muted-foreground">This county&apos;s trend</div>
          <div className="font-medium tabular-nums text-foreground">{fmtBu(data.trend_contribution_bu_acre)}</div>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={Math.max(220, rows.length * 34)}>
        <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 24, left: 4, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" horizontal={false} />
          <XAxis
            type="number"
            tick={{ fontSize: 11, fill: "var(--color-muted-foreground)" }}
            label={{ value: "bu/acre impact", position: "insideBottom", offset: -4, fontSize: 10, fill: "var(--color-muted-foreground)" }}
          />
          <YAxis
            type="category"
            dataKey="name"
            width={170}
            tick={{ fontSize: 11, fill: "var(--color-foreground)" }}
          />
          <Tooltip
            contentStyle={{
              background: "var(--color-card)",
              border: "1px solid var(--color-border)",
              borderRadius: 8,
              fontSize: 12,
            }}
            formatter={(value) => [fmtBu(Number(value)), "Impact"]}
          />
          {/* barSize is explicit -- Recharts' automatic band-width
              computation has repeatedly collapsed to zero width in this
              codebase (see model-accuracy-chart.tsx); setting it directly
              renders reliably regardless of category count. */}
          <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={20}>
            {rows.map((r, i) => (
              <Cell key={i} fill={r.value >= 0 ? "var(--color-primary)" : "var(--color-accent)"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      {data.other_feature_count > 0 && (
        <p className="mt-2 text-center text-xs text-muted-foreground">
          + {data.other_feature_count} smaller factors, combined {fmtBu(data.other_contribution_bu_acre)}
        </p>
      )}
      <p className="mt-1 text-center text-xs text-muted-foreground">
        Baseline + trend + all factors = {fmtBu(data.predicted_yield_bu_acre)} predicted
      </p>
    </div>
  );
}
