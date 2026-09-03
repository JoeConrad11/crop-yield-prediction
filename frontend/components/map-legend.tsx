// Scale legend for the choropleth -- per UX guidance, a color-only map is an
// accessibility risk; a labeled legend plus the tooltip's exact numbers are
// the fallback (see also each county's native accessible name in the map).
export function MapLegend({
  min,
  max,
  unit,
  colorAt,
}: {
  min: number;
  max: number;
  unit: string;
  colorAt: (value: number) => string;
}) {
  const steps = 6;
  const stops = Array.from({ length: steps }, (_, i) => min + ((max - min) * i) / (steps - 1));

  return (
    <div className="pointer-events-none absolute bottom-4 left-4 rounded-lg border border-border bg-card/90 px-3 py-2 text-xs shadow-sm backdrop-blur-sm">
      <div className="mb-1 font-medium text-card-foreground">Predicted yield ({unit})</div>
      <div className="flex h-3 w-40 overflow-hidden rounded">
        {stops.map((v, i) => (
          <div key={i} className="flex-1" style={{ backgroundColor: colorAt(v) }} />
        ))}
      </div>
      <div className="mt-1 flex justify-between text-muted-foreground tabular-nums">
        <span>{min.toFixed(0)}</span>
        <span>{max.toFixed(0)}</span>
      </div>
    </div>
  );
}
