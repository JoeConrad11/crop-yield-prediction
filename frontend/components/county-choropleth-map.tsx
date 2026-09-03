"use client";

import { useQuery } from "@tanstack/react-query";
import { geoAlbersUsa } from "d3-geo";
import { interpolateRgb } from "d3-interpolate";
import { scaleSequential } from "d3-scale";
import { Minus, Plus, RotateCcw } from "lucide-react";
import { useMemo, useState } from "react";
import { ComposableMap, Geographies, Geography, ZoomableGroup } from "react-simple-maps";

import { fetchCountyGeoJSON, fetchLatestPredictions, fetchStatesGeoJSON } from "@/lib/api-client";
import { countyKey } from "@/lib/fips";

import { MapLegend } from "./map-legend";

// Internal SVG coordinate space the projection is fitted into (see
// `projection` below) -- react-simple-maps scales this to fill whatever
// CSS box the map renders in, so these numbers only need to roughly match
// the panel's aspect ratio, not the actual pixel size.
const MAP_WIDTH = 960;
const MAP_HEIGHT = 560;

// Two-color gradient for predicted yield: low = accent gold ("watch this
// one"), high = primary green ("healthy"). Hardcoded to match the hex
// values in app/globals.css --color-accent/--color-primary -- d3-interpolate
// needs concrete colors, not CSS var() references.
const YIELD_COLOR_LOW = "#a16207";
const YIELD_COLOR_HIGH = "#15803d";

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
  const [focusedKey, setFocusedKey] = useState<string | null>(null);
  // A real point inside our data (roughly central IA/IL/NE), not [0,0] --
  // geoAlbersUsa returns null for points outside the US it doesn't cover,
  // and ZoomableGroup's internal effect crashes projecting a null center
  // the moment zoom/center changes (see zoomBy/resetView below).
  const DEFAULT_CENTER: [number, number] = [-92, 40];
  const [zoom, setZoom] = useState({ center: DEFAULT_CENTER, zoom: 1 });

  function zoomBy(factor: number) {
    setZoom((z) => ({ ...z, zoom: Math.min(10, Math.max(1, z.zoom * factor)) }));
  }

  function resetView() {
    setZoom({ center: DEFAULT_CENTER, zoom: 1 });
  }

  const geoQuery = useQuery({
    queryKey: ["geo", "counties"],
    queryFn: () => fetchCountyGeoJSON(),
    staleTime: Infinity, // boundaries don't change between sessions
  });

  // Backdrop only -- gray context so the 4 project states don't render as
  // shapes floating in empty space. Not interactive, not colored by data.
  const statesQuery = useQuery({
    queryKey: ["geo", "states"],
    queryFn: () => fetchStatesGeoJSON(),
    staleTime: Infinity,
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
    const scale = scaleSequential(interpolateRgb(YIELD_COLOR_LOW, YIELD_COLOR_HIGH)).domain(domain);
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
        aria-label={`County-level predicted ${crop} yield, gold means lower yield and green means higher yield. Scroll to zoom, drag to pan, click a county to see its trend.`}
      >
        <ZoomableGroup
          center={zoom.center}
          zoom={zoom.zoom}
          minZoom={1}
          maxZoom={10}
          // Bounds panning in pixel space so the implied geographic center
          // can't drift to a point outside geoAlbersUsa's domain (which
          // returns null there and crashes the library's internal zoom
          // effect -- see DEFAULT_CENTER above for the same underlying issue).
          translateExtent={[
            [-MAP_WIDTH * 0.5, -MAP_HEIGHT * 0.5],
            [MAP_WIDTH * 1.5, MAP_HEIGHT * 1.5],
          ]}
          onMoveEnd={({ coordinates, zoom: z }) => setZoom({ center: coordinates, zoom: z })}
        >
          {statesQuery.data && (
            <Geographies geography={statesQuery.data}>
              {({ geographies }) =>
                geographies.map((geo) => (
                  <Geography
                    key={geo.rsmKey}
                    geography={geo}
                    fill="var(--color-muted)"
                    stroke="var(--color-border)"
                    strokeWidth={0.5 / zoom.zoom}
                    style={{ default: { outline: "none", pointerEvents: "none" } }}
                  />
                ))
              }
            </Geographies>
          )}
          <Geographies geography={geoQuery.data}>
            {({ geographies }) =>
              geographies.map((geo) => {
                const key = countyKey(geo.properties.state_fips, geo.properties.county_fips);
                const entry = byCounty.get(key);
                const isSelected = key === selectedKey;
                const isFocused = key === focusedKey;
                const select = () =>
                  onSelectCounty({
                    stateFips: geo.properties.state_fips,
                    countyFips: geo.properties.county_fips,
                    countyName: geo.properties.county_name,
                  });
                return (
                  <Geography
                    key={geo.rsmKey}
                    geography={geo}
                    fill={entry ? colorAt(entry.value) : "var(--color-muted)"}
                    stroke={isSelected ? "var(--color-accent)" : isFocused ? "var(--color-secondary)" : "var(--color-border)"}
                    strokeWidth={(isSelected || isFocused ? 2.5 : 0.75) / zoom.zoom}
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
                    onClick={select}
                    onFocus={() => setFocusedKey(key)}
                    onBlur={() => setFocusedKey((k) => (k === key ? null : k))}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        select();
                      }
                    }}
                    aria-label={`${geo.properties.county_name}${entry ? `, ${entry.value.toFixed(1)} bu/acre, ${entry.coverageTier ?? ""} coverage` : ", no prediction yet"}`}
                    // Keyboard focus needs a visible indicator (WCAG) -- the
                    // secondary-colored stroke above IS that indicator, so
                    // it's safe to suppress the default browser outline
                    // (which draws a rectangle around the whole path's
                    // bounding box and looks broken on irregular shapes).
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

      <div className="absolute right-4 top-4 flex flex-col overflow-hidden rounded-lg border border-border bg-card shadow-sm">
        <button
          type="button"
          onClick={() => zoomBy(1.5)}
          aria-label="Zoom in"
          className="cursor-pointer border-b border-border p-2 text-foreground transition-colors hover:bg-muted"
        >
          <Plus size={14} />
        </button>
        <button
          type="button"
          onClick={() => zoomBy(1 / 1.5)}
          aria-label="Zoom out"
          className="cursor-pointer border-b border-border p-2 text-foreground transition-colors hover:bg-muted"
        >
          <Minus size={14} />
        </button>
        <button
          type="button"
          onClick={resetView}
          aria-label="Reset map view"
          className="cursor-pointer p-2 text-foreground transition-colors hover:bg-muted"
        >
          <RotateCcw size={14} />
        </button>
      </div>

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
