import type { ReactNode } from "react";

// One consistent header for every My Farm section: title, a one-line
// explanation, and an optional action (e.g. "Add field") on the right.
export function SectionHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3 border-b border-border pb-3">
      <div>
        <h2 className="font-heading text-xl font-semibold text-foreground">
          {title}
        </h2>
        {subtitle && (
          <p className="mt-0.5 text-sm text-muted-foreground">{subtitle}</p>
        )}
      </div>
      {action}
    </div>
  );
}
