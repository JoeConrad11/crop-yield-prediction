"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";

import { fetchCrops } from "@/lib/api-client";
import { cn } from "@/lib/utils";

// Renders whatever GET /crops returns -- no hardcoded crop names, so a
// third crop added to src/config.py CROPS shows up here with zero changes.
export function CropSelector({ selected }: { selected: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { data: crops, isLoading, isError } = useQuery({
    queryKey: ["crops"],
    queryFn: fetchCrops,
    staleTime: Infinity, // crop metadata doesn't change during a session
  });

  function selectCrop(cropId: string) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("crop", cropId);
    router.push(`?${params.toString()}`, { scroll: false });
  }

  if (isLoading) {
    return <div className="h-10 w-48 animate-pulse rounded-lg bg-muted" />;
  }

  if (isError || !crops) {
    return <p className="text-sm text-destructive">Couldn&apos;t load crop list.</p>;
  }

  return (
    <div role="radiogroup" aria-label="Select crop" className="flex gap-2">
      {crops.map((crop) => (
        <button
          key={crop.id}
          type="button"
          role="radio"
          aria-checked={crop.id === selected}
          onClick={() => selectCrop(crop.id)}
          className={cn(
            "cursor-pointer rounded-lg px-4 py-2 text-sm font-medium transition-colors duration-200",
            crop.id === selected
              ? "bg-primary text-primary-foreground"
              : "bg-muted text-muted-foreground hover:bg-secondary hover:text-secondary-foreground"
          )}
        >
          {crop.display_name}
        </button>
      ))}
    </div>
  );
}
