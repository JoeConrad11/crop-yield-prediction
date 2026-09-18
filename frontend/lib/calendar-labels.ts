// Plain-language names for the anchor dates the calendar knowledge uses
// (see src/calendar_knowledge/*.json). Unknown kinds fall back to a
// humanized version, so a new rule's anchor still renders without a change
// here.
const ANCHOR_LABELS: Record<string, string> = {
  lambed: "Lambing date (actual)",
  lambing_due: "Expected lambing date",
  breeding_start: "Breeding start date",
  weaning_planned: "Planned weaning date",
  purchased: "Purchase date",
};

export function anchorLabel(kind: string): string {
  return ANCHOR_LABELS[kind] ?? kind.replace(/_/g, " ");
}

export function speciesLabel(species: string): string {
  return species.charAt(0).toUpperCase() + species.slice(1);
}

// ISO dates (YYYY-MM-DD) are read as local calendar days, not UTC instants,
// so a due date never shifts a day depending on the viewer's timezone.
export function formatDay(iso: string, withYear = false): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    ...(withYear ? { year: "numeric" } : {}),
  });
}

export function formatRange(from: string, to: string): string {
  return from === to ? formatDay(from) : `${formatDay(from)} – ${formatDay(to)}`;
}
