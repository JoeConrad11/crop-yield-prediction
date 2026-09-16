"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import type * as Leaflet from "leaflet";
import { LocateFixed, Search, Trash2, Undo2 } from "lucide-react";

import "leaflet/dist/leaflet.css";
import { polygonAcres, type LatLng } from "@/lib/geo";

type Props = {
  initial?: LatLng[];
  onChange: (points: LatLng[], acres: number) => void;
};

const DEFAULT_CENTER: LatLng = { lat: 41.6, lng: -93.6 }; // Iowa-ish, just a starting viewport

// Esri World Imagery -- free, no API key/account needed (unlike Mapbox/
// Google), and unlike a plain OpenStreetMap road layer it's actual aerial
// imagery, which is the whole point here: a farmer can't trace their
// field's real edge against street labels, they need to see the field.
const SATELLITE_TILE_URL =
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
const SATELLITE_ATTRIBUTION =
  "Tiles &copy; Esri &mdash; Esri, Maxar, Earthstar Geographics, and the GIS User Community";

const VERTEX_STYLE = { radius: 7, color: "#facc15", fillColor: "#15803d", fillOpacity: 1, weight: 3 };

// Deliberately not react-leaflet + Leaflet.draw: both have had rocky React 19
// compatibility, and the interaction this needs (click to place a corner,
// click again to close the ring) is simple enough to drive directly against
// vanilla Leaflet without either dependency. `leaflet` is dynamically
// imported inside the effect because it touches `window` at module load --
// a static import would break Next's server render of this "use client"
// component.
export function FieldMap({ initial = [], onChange }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Leaflet.Map | null>(null);
  const pointsRef = useRef<LatLng[]>(initial);
  const polygonLayerRef = useRef<Leaflet.Polygon | null>(null);
  const vertexLayersRef = useRef<Leaflet.CircleMarker[]>([]);
  const clearRef = useRef<() => void>(() => {});
  const undoRef = useRef<() => void>(() => {});
  const locateRef = useRef<() => void>(() => {});
  const flyToRef = useRef<(lat: number, lng: number) => void>(() => {});
  const [pointCount, setPointCount] = useState(initial.length);
  const [searchText, setSearchText] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState("");

  useEffect(() => {
    let cancelled = false;

    import("leaflet").then((mod) => {
      if (cancelled || !containerRef.current || mapRef.current) return;
      const L = mod.default;

      const start = initial[0] ?? DEFAULT_CENTER;
      const map = L.map(containerRef.current, { zoomControl: false }).setView([start.lat, start.lng], 16);
      L.control.zoom({ position: "bottomright" }).addTo(map);
      L.tileLayer(SATELLITE_TILE_URL, { maxZoom: 20, attribution: SATELLITE_ATTRIBUTION }).addTo(map);
      mapRef.current = map;

      function redraw() {
        polygonLayerRef.current?.remove();
        polygonLayerRef.current = null;
        if (pointsRef.current.length >= 3) {
          polygonLayerRef.current = L.polygon(
            pointsRef.current.map((p) => [p.lat, p.lng]),
            { color: "#facc15", weight: 3, fillColor: "#15803d", fillOpacity: 0.35 }
          ).addTo(map);
        }
        setPointCount(pointsRef.current.length);
        onChange(pointsRef.current, polygonAcres(pointsRef.current));
      }

      function addVertex(latlng: Leaflet.LatLng) {
        pointsRef.current = [...pointsRef.current, { lat: latlng.lat, lng: latlng.lng }];
        const marker = L.circleMarker(latlng, VERTEX_STYLE).addTo(map);
        vertexLayersRef.current.push(marker);
        redraw();
      }

      map.on("click", (e: Leaflet.LeafletMouseEvent) => addVertex(e.latlng));

      initial.forEach((p) => {
        vertexLayersRef.current.push(L.circleMarker([p.lat, p.lng], VERTEX_STYLE).addTo(map));
      });
      if (initial.length) redraw();

      clearRef.current = () => {
        vertexLayersRef.current.forEach((m) => m.remove());
        vertexLayersRef.current = [];
        pointsRef.current = [];
        redraw();
      };
      undoRef.current = () => {
        vertexLayersRef.current.pop()?.remove();
        pointsRef.current = pointsRef.current.slice(0, -1);
        redraw();
      };
      locateRef.current = () => {
        if (!navigator.geolocation) return;
        navigator.geolocation.getCurrentPosition((pos) => {
          map.setView([pos.coords.latitude, pos.coords.longitude], 18);
        });
      };
      flyToRef.current = (lat, lng) => {
        map.setView([lat, lng], 17);
      };
    });

    return () => {
      cancelled = true;
      mapRef.current?.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Nominatim (OSM's free geocoder) -- no API key, fine at the request
  // volume a single farmer typing their own address generates.
  async function handleSearch(e: FormEvent) {
    e.preventDefault();
    if (!searchText.trim()) return;
    setSearching(true);
    setSearchError("");
    try {
      const res = await fetch(
        `https://nominatim.openstreetmap.org/search?format=json&limit=1&q=${encodeURIComponent(searchText)}`
      );
      const results = (await res.json()) as Array<{ lat: string; lon: string }>;
      if (!results.length) {
        setSearchError("No match found -- try zooming/panning manually instead.");
        return;
      }
      flyToRef.current(parseFloat(results[0].lat), parseFloat(results[0].lon));
    } catch {
      setSearchError("Search failed -- try zooming/panning manually instead.");
    } finally {
      setSearching(false);
    }
  }

  return (
    <div className="space-y-2">
      <form onSubmit={handleSearch} className="flex gap-2">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            placeholder="Jump to an address or town..."
            className="w-full rounded-lg border border-border bg-card py-1.5 pl-8 pr-2 text-sm text-card-foreground outline-none focus:border-primary"
          />
        </div>
        <button
          type="submit"
          disabled={searching}
          className="rounded-lg border border-border bg-card px-3 text-sm text-muted-foreground transition-colors hover:bg-muted disabled:opacity-50"
        >
          {searching ? "..." : "Go"}
        </button>
        <button
          type="button"
          onClick={() => locateRef.current()}
          title="Center on my location"
          className="flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 text-sm text-muted-foreground transition-colors hover:bg-muted"
        >
          <LocateFixed className="size-3.5" aria-hidden="true" />
        </button>
      </form>
      {searchError && <p className="text-xs text-destructive">{searchError}</p>}

      <div className="relative">
        <div ref={containerRef} className="h-[26rem] w-full overflow-hidden rounded-xl border border-accent/40" />
        <div className="pointer-events-none absolute left-3 top-3 z-[1000] rounded-lg bg-background/90 px-2.5 py-1.5 text-xs text-foreground shadow-sm backdrop-blur-sm">
          Click your field&apos;s corners in order &mdash; {pointCount < 3 ? `${3 - pointCount} more to go` : `${pointCount} points`}
        </div>
        <div className="absolute right-3 top-3 z-[1000] flex gap-1.5">
          <button
            type="button"
            onClick={() => undoRef.current()}
            disabled={pointCount === 0}
            title="Undo last point"
            className="flex items-center justify-center rounded-lg bg-background/90 p-2 text-foreground shadow-sm backdrop-blur-sm transition-colors hover:bg-muted disabled:opacity-40"
          >
            <Undo2 className="size-3.5" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => clearRef.current()}
            disabled={pointCount === 0}
            title="Clear all points"
            className="flex items-center justify-center rounded-lg bg-background/90 p-2 text-destructive shadow-sm backdrop-blur-sm transition-colors hover:bg-muted disabled:opacity-40"
          >
            <Trash2 className="size-3.5" aria-hidden="true" />
          </button>
        </div>
      </div>
    </div>
  );
}
