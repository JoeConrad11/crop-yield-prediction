import type { CountyComparison } from "@/lib/types";
import { cn } from "@/lib/utils";

const currency = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

const TIER_STYLE: Record<string, string> = {
  high: "bg-primary/10 text-primary",
  medium: "bg-accent/15 text-accent",
  low: "bg-muted text-muted-foreground",
};

// Renders one county's crops generically -- Object.entries(crops), not a
// fixed corn/soybean pair, so a third crop just adds another row.
export function ComparisonCard({
  county,
  coverageByCrop,
  selected,
  onSelect,
}: {
  county: CountyComparison;
  coverageByCrop?: Record<string, string | null>;
  selected?: boolean;
  onSelect?: () => void;
}) {
  const cropEntries = Object.entries(county.crops);

  return (
    <button
      type="button"
      id={`county-${county.state_fips}-${county.county_fips}`}
      onClick={onSelect}
      className={cn(
        "w-full cursor-pointer rounded-xl border bg-card p-4 text-left shadow-sm transition-colors duration-150",
        selected ? "border-accent ring-2 ring-accent/40" : "border-border hover:border-secondary"
      )}
    >
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="font-heading text-base font-semibold text-card-foreground">
          {county.county_name}, {county.state_alpha}
        </h3>
        {county.best_crop && (
          <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
            Best: {county.best_crop}
          </span>
        )}
      </div>

      <dl className="mt-3 space-y-2">
        {cropEntries.map(([cropId, fields]) => {
          const tier = coverageByCrop?.[cropId];
          return (
            <div
              key={cropId}
              className={cn(
                "flex items-center justify-between rounded-lg px-2 py-1.5 text-sm",
                cropId === county.best_crop && "bg-secondary/15"
              )}
            >
              <dt className="flex items-center gap-1.5 capitalize text-muted-foreground">
                {cropId}
                {tier && (
                  <span className={cn("rounded-full px-1.5 py-0.5 text-[10px] font-medium capitalize", TIER_STYLE[tier] ?? TIER_STYLE.low)}>
                    {tier}
                  </span>
                )}
              </dt>
              <dd className="tabular-nums font-medium text-card-foreground">
                {fields.profit_per_acre !== null ? currency.format(fields.profit_per_acre) : "--"}
                <span className="ml-1 text-xs font-normal text-muted-foreground">/acre</span>
              </dd>
            </div>
          );
        })}
      </dl>

      {county.margin_dollars !== null && (
        <p className="mt-2 text-xs text-muted-foreground">
          Margin over next best: {currency.format(county.margin_dollars)}/acre
        </p>
      )}
      <p className="mt-1 text-[10px] text-muted-foreground/70">Click to see yield trend</p>
    </button>
  );
}
