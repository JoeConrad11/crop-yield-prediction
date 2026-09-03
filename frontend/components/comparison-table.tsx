"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowUpDown, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { fetchComparisons, fetchLatestPredictions } from "@/lib/api-client";
import { countyKey } from "@/lib/fips";

import { ComparisonCard } from "./comparison-card";

const PAGE_SIZE = 30;

type SortMode = "margin" | "name";

export function ComparisonTable({
  selectedKey,
  onSelectCounty,
}: {
  selectedKey: string | null;
  onSelectCounty: (info: { stateFips: string; countyFips: string; countyName: string }) => void;
}) {
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortMode>("margin");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const selectedRef = useRef<HTMLDivElement>(null);

  const { data: counties, isLoading, isError } = useQuery({
    queryKey: ["comparisons"],
    queryFn: () => fetchComparisons(),
  });

  // Unfiltered so every crop's coverage tier is available per county, not
  // just whichever crop happens to be selected on the map.
  const { data: allPredictions } = useQuery({
    queryKey: ["predictions", "latest", "all"],
    queryFn: () => fetchLatestPredictions({}),
  });

  const coverageByCounty = useMemo(() => {
    const map = new Map<string, Record<string, string | null>>();
    for (const row of allPredictions ?? []) {
      const key = countyKey(row.state_fips, row.county_fips);
      const entry = map.get(key) ?? {};
      entry[row.crop] = row.coverage_tier;
      map.set(key, entry);
    }
    return map;
  }, [allPredictions]);

  const filtered = useMemo(() => {
    if (!counties) return [];
    const q = search.trim().toLowerCase();
    let rows = q
      ? counties.filter(
          (c) => c.county_name.toLowerCase().includes(q) || c.state_alpha.toLowerCase().includes(q)
        )
      : counties;
    rows = [...rows].sort((a, b) => {
      if (sort === "name") return a.county_name.localeCompare(b.county_name);
      return (b.margin_dollars ?? -Infinity) - (a.margin_dollars ?? -Infinity);
    });
    return rows;
  }, [counties, search, sort]);

  // Scroll the selected county's card into view when it's picked from the map.
  useEffect(() => {
    if (selectedKey && selectedRef.current) {
      selectedRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [selectedKey]);

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-24 animate-pulse rounded-xl bg-muted" />
        ))}
      </div>
    );
  }

  if (isError || !counties) {
    return <p className="text-sm text-destructive">Couldn&apos;t load county comparisons. Retry shortly.</p>;
  }

  const visible = filtered.slice(0, visibleCount);

  return (
    <div>
      <div className="mb-3 flex gap-2">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" size={14} />
          <input
            type="search"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setVisibleCount(PAGE_SIZE);
            }}
            placeholder="Search county or state..."
            className="w-full rounded-lg border border-border bg-card py-1.5 pl-8 pr-2 text-sm text-card-foreground outline-none focus:border-primary"
          />
        </div>
        <button
          type="button"
          onClick={() => setSort((s) => (s === "margin" ? "name" : "margin"))}
          className="flex cursor-pointer items-center gap-1 rounded-lg border border-border bg-card px-2.5 text-xs text-muted-foreground transition-colors hover:bg-muted"
          title="Toggle sort"
        >
          <ArrowUpDown size={12} />
          {sort === "margin" ? "Margin" : "Name"}
        </button>
      </div>

      {filtered.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No counties match &quot;{search}&quot;. Try a different county or state name.
        </p>
      ) : (
        <>
          <div className="space-y-3">
            {visible.map((county) => {
              const key = countyKey(county.state_fips, county.county_fips);
              const isSelected = key === selectedKey;
              return (
                <div key={key} ref={isSelected ? selectedRef : undefined}>
                  <ComparisonCard
                    county={county}
                    coverageByCrop={coverageByCounty.get(key)}
                    selected={isSelected}
                    onSelect={() =>
                      onSelectCounty({
                        stateFips: county.state_fips,
                        countyFips: county.county_fips,
                        countyName: county.county_name,
                      })
                    }
                  />
                </div>
              );
            })}
          </div>
          {visibleCount < filtered.length && (
            <button
              type="button"
              onClick={() => setVisibleCount((c) => c + PAGE_SIZE)}
              className="mt-3 w-full cursor-pointer rounded-lg border border-border bg-card py-2 text-sm text-muted-foreground transition-colors hover:bg-muted"
            >
              Show more ({filtered.length - visibleCount} remaining)
            </button>
          )}
        </>
      )}
    </div>
  );
}
