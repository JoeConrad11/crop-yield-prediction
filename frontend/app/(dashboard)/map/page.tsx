import { Suspense } from "react";

import { MapDashboard } from "@/components/map-dashboard";

// MapDashboard uses useSearchParams (client-only, driven by ?crop=) --
// Suspense boundary required per Next.js docs for a page-level consumer.
export default function MapPage() {
  return (
    <Suspense fallback={<div className="flex min-h-dvh items-center justify-center">Loading...</div>}>
      <MapDashboard />
    </Suspense>
  );
}
