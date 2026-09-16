"use client";

import { FlaskConical, Lock, Map as MapIcon, MapPinned, ScrollText } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/map", label: "Map", icon: MapIcon },
  { href: "/pipeline", label: "Pipeline API", icon: FlaskConical },
];

function NavLink({ href, label, icon: Icon, active }: { href: string; label: string; icon: typeof MapIcon; active: boolean }) {
  return (
    <Link
      href={href}
      className={cn(
        "flex cursor-pointer items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors duration-200",
        active
          ? "bg-primary text-primary-foreground"
          : "text-primary underline-offset-4 hover:bg-muted hover:underline"
      )}
    >
      <Icon className="size-4" aria-hidden="true" />
      {label}
    </Link>
  );
}

/** Shared top nav for every page in the app, so a feature like the pipeline
 * API demo reads as part of the product rather than a bolted-on page. */
export function AppHeader({ subtitle, children }: { subtitle: string; children?: ReactNode }) {
  const pathname = usePathname();
  const farmLocked = process.env.NEXT_PUBLIC_LOCK_FARM_FEATURES === "true";

  return (
    <header className="flex flex-col gap-2 border-b border-border bg-card px-4 py-2.5 sm:flex-row sm:items-center sm:justify-between sm:px-6">
      <div>
        <Link
          href="/map"
          className="font-heading text-lg font-semibold text-card-foreground transition-colors duration-200 hover:text-primary"
        >
          Crop Yield Predictor
        </Link>
        <p className="text-xs text-muted-foreground">{subtitle}</p>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        {children}
        {NAV_ITEMS.map((item) => (
          <NavLink key={item.href} {...item} active={pathname === item.href} />
        ))}
        {farmLocked ? (
          <span
            title="Locked for this deployment"
            aria-disabled="true"
            className="flex cursor-not-allowed items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-muted-foreground/50 blur-[1.5px] select-none"
          >
            <Lock className="size-4" aria-hidden="true" />
            My Farm
          </span>
        ) : (
          <NavLink href="/farm" label="My Farm" icon={MapPinned} active={pathname === "/farm"} />
        )}
        <a
          href={process.env.NEXT_PUBLIC_DATA_EXPLORER_URL ?? "https://ag-data-explorer.vercel.app"}
          target="_blank"
          rel="noopener noreferrer"
          className="flex cursor-pointer items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-foreground shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md"
        >
          <ScrollText className="size-4" aria-hidden="true" />
          The Harvest Ledger
        </a>
      </div>
    </header>
  );
}
