export type LatLng = { lat: number; lng: number };

export interface GeoJSONPolygon {
  type: "Polygon";
  coordinates: number[][][];
}

// Equirectangular projection centered on the polygon's own average latitude,
// then a planar shoelace formula. Accurate to well under 1% at field scale
// (a few hundred acres, one small patch of the globe) -- plenty for a
// figure the farmer sees as "~42 acres" next to a map they drew themselves,
// not a legal survey. Avoids pulling in a full geodesy library for that.
export function polygonAcres(points: LatLng[]): number {
  if (points.length < 3) return 0;

  const EARTH_RADIUS_M = 6378137;
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const avgLat = points.reduce((sum, p) => sum + p.lat, 0) / points.length;
  const cosLat = Math.cos(toRad(avgLat));

  const projected = points.map((p) => ({
    x: toRad(p.lng) * EARTH_RADIUS_M * cosLat,
    y: toRad(p.lat) * EARTH_RADIUS_M,
  }));

  let twiceArea = 0;
  for (let i = 0; i < projected.length; i++) {
    const a = projected[i];
    const b = projected[(i + 1) % projected.length];
    twiceArea += a.x * b.y - b.x * a.y;
  }

  const squareMeters = Math.abs(twiceArea) / 2;
  return squareMeters / 4046.8564224; // m^2 per acre
}

// Field boundaries round-trip through this shape end to end: Leaflet emits
// {lat,lng} points, GeoJSON (what's persisted, and what Phase 2's
// ee.Geometry will consume directly) wants [lng,lat] rings closed back on
// their first point.
export function polygonToGeoJSON(points: LatLng[]): GeoJSONPolygon {
  const ring = points.map((p) => [p.lng, p.lat]);
  const [firstLng, firstLat] = ring[0];
  const [lastLng, lastLat] = ring[ring.length - 1];
  if (firstLng !== lastLng || firstLat !== lastLat) {
    ring.push([firstLng, firstLat]);
  }
  return { type: "Polygon", coordinates: [ring] };
}

export function geoJSONToLatLngs(polygon: GeoJSONPolygon): LatLng[] {
  const ring = polygon.coordinates[0] ?? [];
  const [firstLng, firstLat] = ring[0] ?? [];
  const [lastLng, lastLat] = ring[ring.length - 1] ?? [];
  const open = ring.length > 1 && firstLng === lastLng && firstLat === lastLat ? ring.slice(0, -1) : ring;
  return open.map(([lng, lat]) => ({ lat, lng }));
}
