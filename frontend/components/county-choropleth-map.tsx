"use client";

import { useQuery } from "@tanstack/react-query";
import { scaleSequential } from "d3-scale";
import { interpolateGreens } from "d3-scale-chromatic";
import { geoAlbersUsa } from "d3-geo";
import { useMemo, useState } from "react";
import { ComposableMap, Geographies, Geography, ZoomableGroup } from "react-simple-maps";

import { fetchCountyGeoJSON, fetchLatestPredictions } from "@/lib/api-client";
import { countyKey } from "@/lib/fips";

import { MapLegend } from "./map-legend";

// Internal SVG coordinate space the projection is fitted into (see
// `projection` below) -- react-simple-maps scales this to fill whatever
// CSS box the map renders in, so these numbers only need to roughly match
// the panel's aspect ratio, not the actual pixel size.
const MAP_WIDTH = 960;
const MAP_HEIGHT = 560;

type HoverInfo = {
  x: number;
  y: number;
  countyName: string;
  stateFips: string;
  value: number | undefined;
  coverageTier: string | null | undefined;
};

// Parameterized by `crop` (an id from GET /crops) -- one component for
// however many crops exist, not a per-crop map variant.
export function CountyChoroplethMap({
  crop,
  selectedKey,
  onSelectCounty,
}: {
  crop: string;
  selectedKey: string | null;
  onSelectCounty: (info: { stateFips: string; countyFips: string; countyName: string }) => void;
}) {
  const [hover, setHover] = useState<HoverInfo | null>(null);
  const [zoom, setZoom] = useState({ center: [0, 0] as [number, number], zoom: 1 });

  const geoQuery = useQuery({
    queryKey: ["geo", "counties"],
    queryFn: () => fetchCountyGeoJSON(),
    staleTime: Infinity, // boundaries don't change between sessions
  });

  const predictionsQuery = useQuery({
    queryKey: ["predictions", "latest", crop],
    queryFn: () => fetchLatestPredictions({ crop }),
  });

  // Fit the projection to this project's actual county set instead of the
  // full-country default -- geoAlbersUsa on its own leaves IA/IL/NE/NC as a
  // tiny cluster inside a mostly-empty US-shaped canvas.
  const projection = useMemo(() => {
    if (!geoQuery.data) return null;
    return geoAlbersUsa().fitSize([MAP_WIDTH, MAP_HEIGHT], geoQuery.data as never);
  }, [geoQuery.data]);

  const byCounty = useMemo(() => {
    const map = new Map<string, { value: number; coverageTier: string | null }>();
    for (const row of predictionsQuery.data ?? []) {
      map.set(countyKey(row.state_fips, row.county_fips), {
        value: row.predicted_yield_bu_acre,
        coverageTier: row.coverage_tier,
      });
    }
    return map;
  }, [predictionsQuery.data]);

  const domain = useMemo((): [number, number] => {
    const values = [...byCounty.values()].map((v) => v.value);
    if (values.length === 0) return [0, 1];
    return [Math.min(...values), Math.max(...values)];
  }, [byCounty]);

  const colorAt = useMemo(() => {
    const scale = scaleSequential(interpolateGreens).domain(domain);
    return (value: number) => scale(value);
  }, [domain]);

  if (geoQuery.isLoading || predictionsQuery.isLoading || !projection) {
    return (
      <div className="flex h-full min-h-[400px] items-center justify-center text-muted-foreground">
        Loading map...
      </div>
    );
  }

  if (geoQuery.isError || predictionsQuery.isError) {
    return (
      <div className="flex h-full min-h-[400px] items-center justify-center text-destructive">
        Couldn&apos;t load the map. Retry shortly.
      </div>
    );
  }

  return (
    <div className="relative h-full w-full">
      <ComposableMap
        width={MAP_WIDTH}
        height={MAP_HEIGHT}
        // react-simple-maps uses a function `projection` prop AS the d3
        // projection instance itself (reads `.stream` straight off it) --
        // it does not call it as a (width, height, config) factory despite
        // the published type signature. Passing our already-fitted
        // projection object directly is what actually works at runtime.
        projection={projection as never}
        className="h-full w-full cursor-grab active:cursor-grabbing"
        role="img"
        aria-label={`County-level predicted ${crop} yield, darker green means higher yield. Scroll to zoom, drag to pan, click a county to see its trend.`}
      >
        <ZoomableGroup
          center={zoom.center}
          zoom={zoom.zoom}
          minZoom={1}
          maxZoom={10}
          onMoveEnd={({ coordinates, zoom: z }) => setZoom({ center: coordinates, zoom: z })}
        >
          <Geographies geography={geoQuery.data}>
            {({ geographies }) =>
              geographies.map((geo) => {
                const key = countyKey(geo.properties.state_fips, geo.properties.county_fips);
                const entry = byCounty.get(key);
                const isSelected = key === selectedKey;
                return (
                  <Geography
                    key={geo.rsmKey}
                    geography={geo}
                    fill={entry ? colorAt(entry.value) : "var(--color-muted)"}
                    stroke={isSelected ? "var(--color-accent)" : "var(--color-border)"}
                    strokeWidth={(isSelected ? 2.5 : 0.75) / zoom.zoom}
                    onMouseEnter={(e) =>
                      setHover({
                        x: e.clientX,
                        y: e.clientY,
                        countyName: geo.properties.county_name,
                        stateFips: geo.properties.state_fips,
                        value: entry?.value,
                        coverageTier: entry?.coverageTier,
                      })
                    }
                    onMouseMove={(e) => setHover((h) => (h ? { ...h, x: e.clientX, y: e.clientY } : h))}
                    onMouseLeave={() => setHover(null)}
                    onClick={() =>
                      onSelectCounty({
                        stateFips: geo.properties.state_fips,
                        countyFips: geo.properties.county_fips,
                        countyName: geo.properties.county_name,
                      })
                    }
                    style={{
                      default: { outline: "none", cursor: "pointer", transition: "fill 150ms ease" },
                      hover: { outline: "none", fill: "var(--color-secondary)", cursor: "pointer" },
                      pressed: { outline: "none" },
                    }}
                  />
                );
              })
            }
          </Geographies>
        </ZoomableGroup>
      </ComposableMap>

      <MapLegend min={domain[0]} max={domain[1]} unit="bu/acre" colorAt={colorAt} />

      {hover && (
        <div
          className="pointer-events-none fixed z-50 -translate-x-1/2 -translate-y-full rounded-lg border border-border bg-card px-3 py-2 text-xs shadow-lg"
          style={{ left: hover.x, top: hover.y - 8 }}
        >
          <div className="font-medium text-card-foreground">{hover.countyName}</div>
          {hover.value !== undefined ? (
            <>
              <div className="tabular-nums text-muted-foreground">{hover.value.toFixed(1)} bu/acre</div>
              {hover.coverageTier && (
                <div className="capitalize text-muted-foreground">{hover.coverageTier} coverage</div>
              )}
            </>
          ) : (
            <div className="text-muted-foreground">No prediction yet</div>
          )}
          <div className="mt-0.5 text-[10px] text-muted-foreground/70">Click for yield trend</div>
        </div>
      )}
    </div>
  );
}
