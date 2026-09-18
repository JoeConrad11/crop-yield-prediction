"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";

import type { CalendarEntry } from "@/lib/types";

export type DayItem = {
  entry: CalendarEntry;
  kind: "likely" | "window";
  done: boolean;
};

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export const isoDay = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

// Chip colour by what kind of item it is. Overdue overrides so it can't be
// missed; done items fade.
function chipClass(item: DayItem): string {
  if (item.done) return "bg-muted text-muted-foreground line-through";
  if (item.entry.status === "overdue")
    return "bg-destructive/15 text-destructive";
  switch (item.entry.category) {
    case "health":
      return "bg-primary/15 text-primary";
    case "crop_stage":
    case "harvest":
      return "bg-accent/25 text-foreground";
    default:
      return "bg-muted text-foreground";
  }
}

// A real month view. Each item sits on its likely day; when the date is a
// range (a projected crop stage, or a "3 to 4 weeks" window), the other days
// in the range get a small dot so the uncertainty is visible, not hidden.
export function CalendarGrid({
  year,
  month,
  onMonthChange,
  itemsByDay,
  selected,
  onSelect,
  today,
}: {
  year: number;
  month: number; // 0-11
  onMonthChange: (year: number, month: number) => void;
  itemsByDay: Record<string, DayItem[]>;
  selected: string;
  onSelect: (iso: string) => void;
  today: string;
}) {
  const first = new Date(year, month, 1);
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells: (string | null)[] = [
    ...Array(first.getDay()).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) =>
      isoDay(new Date(year, month, i + 1)),
    ),
  ];
  while (cells.length % 7) cells.push(null);

  const shift = (delta: number) => {
    const d = new Date(year, month + delta, 1);
    onMonthChange(d.getFullYear(), d.getMonth());
  };

  return (
    <div className="rounded-xl border border-accent/40 bg-card p-3 shadow-sm">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="font-heading text-base font-semibold text-card-foreground">
          {first.toLocaleDateString(undefined, {
            month: "long",
            year: "numeric",
          })}
        </h3>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => {
              const t = new Date();
              onMonthChange(t.getFullYear(), t.getMonth());
              onSelect(today);
            }}
            className="cursor-pointer rounded-lg px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted"
          >
            Today
          </button>
          <button
            type="button"
            onClick={() => shift(-1)}
            aria-label="Previous month"
            className="cursor-pointer rounded-full p-1.5 text-muted-foreground transition-colors hover:bg-muted"
          >
            <ChevronLeft className="size-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => shift(1)}
            aria-label="Next month"
            className="cursor-pointer rounded-full p-1.5 text-muted-foreground transition-colors hover:bg-muted"
          >
            <ChevronRight className="size-4" aria-hidden="true" />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-7 gap-px overflow-hidden rounded-lg border border-border bg-border text-xs">
        {WEEKDAYS.map((w) => (
          <div
            key={w}
            className="bg-muted/50 py-1 text-center font-medium text-muted-foreground"
          >
            {w}
          </div>
        ))}
        {cells.map((iso, i) => {
          if (!iso)
            return (
              <div
                key={`blank-${i}`}
                className="min-h-14 bg-card/60 sm:min-h-20"
              />
            );
          const items = itemsByDay[iso] ?? [];
          const likely = items.filter((x) => x.kind === "likely");
          const windowCount = items.length - likely.length;
          const isToday = iso === today;
          return (
            <button
              key={iso}
              type="button"
              onClick={() => onSelect(iso)}
              aria-label={`${iso}, ${items.length} item${items.length === 1 ? "" : "s"}`}
              className={`flex min-h-14 cursor-pointer flex-col gap-0.5 bg-card p-1 text-left transition-colors hover:bg-muted/40 sm:min-h-20 ${
                iso === selected ? "ring-2 ring-inset ring-primary" : ""
              }`}
            >
              <span
                className={`flex size-5 items-center justify-center self-end rounded-full text-[11px] ${
                  isToday
                    ? "bg-primary font-semibold text-primary-foreground"
                    : "text-muted-foreground"
                }`}
              >
                {Number(iso.slice(8))}
              </span>
              {likely.slice(0, 2).map((item) => (
                <span
                  key={`${item.entry.rule_id}-${item.entry.subject_id}`}
                  className={`hidden truncate rounded px-1 text-[10px] leading-4 sm:block ${chipClass(item)}`}
                >
                  {item.entry.title}
                </span>
              ))}
              {/* phone width: dots instead of text chips */}
              {!!likely.length && (
                <span className="flex flex-wrap gap-0.5 sm:hidden">
                  {likely.slice(0, 4).map((item) => (
                    <span
                      key={`d-${item.entry.rule_id}-${item.entry.subject_id}`}
                      className={`size-1.5 rounded-full ${chipClass(item).split(" ")[0]}`}
                    />
                  ))}
                </span>
              )}
              {likely.length > 2 && (
                <span className="hidden text-[10px] text-muted-foreground sm:block">
                  +{likely.length - 2} more
                </span>
              )}
              {windowCount > 0 && !likely.length && (
                <span
                  className="size-1.5 self-start rounded-full bg-muted-foreground/40"
                  aria-hidden="true"
                />
              )}
            </button>
          );
        })}
      </div>
      <p className="mt-2 text-[11px] text-muted-foreground/80">
        Bold chips are the likely day; a grey dot marks other days inside a
        projected date range.
      </p>
    </div>
  );
}
