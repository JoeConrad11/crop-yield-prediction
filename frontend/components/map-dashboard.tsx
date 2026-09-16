"use client";

import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { fetchCrops } from "@/lib/api-client";
import { countyKey } from "@/lib/fips";

import { AppHeader } from "./app-header";
import { ComparisonTable } from "./comparison-table";
import { CountyChoroplethMap } from "./county-choropleth-map";
import { CountyDetailPanel } from "./county-detail-panel";
import { CropSelector } from "./crop-selector";

type Selected = { stateFips: string; countyFips: string; countyName: string };

export function MapDashboard() {
  const searchParams = useSearchParams();
  const { data: crops } = useQuery({ queryKey: ["crops"], queryFn: fetchCrops, staleTime: Infinity });
  const [selected, setSelected] = useState<Selected | null>(null);

  // Falls back to the first crop GET /crops returns -- never a hardcoded
  // crop id -- until the user picks one explicitly via the URL param.
  const selectedCrop = searchParams.get("crop") ?? crops?.[0]?.id ?? "";
  const selectedKey = selected ? countyKey(selected.stateFips, selected.countyFips) : null;

  function handleSelectCounty(info: Selected) {
    setSelected((prev) =>
      prev && prev.stateFips === info.stateFips && prev.countyFips === info.countyFips ? null : info
    );
  }

  return (
    <div className="flex min-h-dvh flex-col">
      <AppHeader subtitle="County-level yield predictions & profit comparisons -- click a county for its trend">
        <CropSelector selected={selectedCrop} />
      </AppHeader>

      <main className="flex flex-1 flex-col lg:flex-row">
        <section className="min-h-[500px] flex-1 lg:h-[calc(100dvh-4.5rem)]" aria-label="Predicted yield map">
          {selectedCrop ? (
            <CountyChoroplethMap crop={selectedCrop} selectedKey={selectedKey} onSelectCounty={handleSelectCounty} />
          ) : (
            <div className="flex h-full items-center justify-center text-muted-foreground">
              Loading crops...
            </div>
          )}
        </section>

        <aside className="w-full overflow-y-auto border-t border-border bg-background p-4 lg:h-[calc(100dvh-4.5rem)] lg:w-80 lg:border-t-0 lg:border-l">
          {selected && selectedCrop && (
            <CountyDetailPanel
              crop={selectedCrop}
              stateFips={selected.stateFips}
              countyFips={selected.countyFips}
              countyName={selected.countyName}
              onClose={() => setSelected(null)}
            />
          )}
          <h2 className="mb-3 font-heading text-sm font-semibold text-foreground">County comparisons</h2>
          <ComparisonTable selectedKey={selectedKey} onSelectCounty={handleSelectCounty} />
        </aside>
      </main>
    </div>
  );
}
