import { Lock } from "lucide-react";

/** Static blurred placeholder shown instead of a real feature (which may
 * hit live auth/Supabase) when that feature is locked for a given
 * deployment -- see LOCK_FARM_FEATURES in farm/page.tsx and login/page.tsx. */
export function LockedFeature({ title }: { title: string }) {
  return (
    <div className="relative flex min-h-dvh items-center justify-center overflow-hidden bg-background px-4">
      <div aria-hidden="true" className="pointer-events-none select-none blur-sm opacity-50">
        <div className="w-80 space-y-3 rounded-xl border border-border bg-card p-6 shadow-sm">
          <div className="h-4 w-2/3 rounded bg-muted" />
          <div className="h-3 w-full rounded bg-muted" />
          <div className="h-3 w-5/6 rounded bg-muted" />
          <div className="h-9 w-full rounded-lg bg-primary/30" />
        </div>
      </div>
      <div className="absolute flex flex-col items-center gap-3 rounded-xl border border-border bg-card/95 px-8 py-6 text-center shadow-lg backdrop-blur-sm">
        <Lock className="size-6 text-muted-foreground" aria-hidden="true" />
        <div>
          <p className="font-heading text-sm font-semibold text-card-foreground">{title}</p>
          <p className="mt-1 text-xs text-muted-foreground">Locked for this deployment</p>
        </div>
      </div>
    </div>
  );
}
