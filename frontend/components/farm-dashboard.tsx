"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, MapPinned, Sprout, Trash2 } from "lucide-react";
import Link from "next/link";

import { supabase } from "@/lib/supabase-client";
import { useSession } from "@/lib/use-session";
import {
  ensureDefaultFarm,
  fetchFields,
  createField,
  deleteField,
  updateFieldSeason,
  fetchHerds,
  fetchFarmEvents,
  fetchCompletions,
} from "@/lib/farm-client";
import { fetchCalendarKnowledge, fetchCrops } from "@/lib/api-client";
import { polygonToGeoJSON, type LatLng } from "@/lib/geo";
import { FieldMap } from "./field-map";
import { FieldPredictionPanel } from "./field-prediction";
import { LivestockPanel } from "./livestock-panel";
import { FarmCalendar } from "./farm-calendar";

// supabase-js errors (PostgrestError, AuthError, ...) aren't real Error
// instances -- they're plain objects with a `.message` string -- so
// `instanceof Error` misses them and the schema-missing 404 above would
// otherwise just show "Unknown error".
function farmErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (error && typeof error === "object" && "message" in error && typeof error.message === "string") {
    return error.message;
  }
  return "Unknown error";
}

// Phase 1 of the farmer-app roadmap (see ../../ARCHITECTURE.md): a farmer
// signs in, draws their own field(s), and those become the geometry Phase
// 2's field-level GEE pulls and Phase 3's personalized predictions key off
// of -- replacing the county-average numbers the rest of this app shows
// today.
export function FarmDashboard() {
  const router = useRouter();
  const { session, loading } = useSession();
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!loading && !session) {
      router.replace("/login");
    }
  }, [loading, session, router]);

  const {
    data: farm,
    error: farmError,
    isError: farmErrored,
  } = useQuery({
    queryKey: ["farm", session?.user.id],
    queryFn: () => ensureDefaultFarm(session!.user.id, session!.user.email ?? undefined),
    enabled: !!session,
    retry: false,
  });

  const { data: fields, isLoading: fieldsLoading } = useQuery({
    queryKey: ["fields", farm?.id],
    queryFn: () => fetchFields(farm!.id),
    enabled: !!farm,
  });

  // Crop list drives both the add-field crop picker and each field's
  // "predict my field" panel (see field-prediction.tsx) -- same GET /crops
  // map-dashboard.tsx already uses, so a new crop in src/config.py shows up
  // in both places with zero frontend changes.
  const { data: crops } = useQuery({ queryKey: ["crops"], queryFn: fetchCrops, staleTime: Infinity });

  // Smart farm calendar inputs (src/supabase_farm_migration_calendar.sql).
  // Kept separate from the field queries so a missing migration only turns
  // off the livestock/calendar sections, never the fields the farmer already
  // has.
  const { data: herds, error: herdsError } = useQuery({
    queryKey: ["herds", farm?.id],
    queryFn: () => fetchHerds(farm!.id),
    enabled: !!farm,
    retry: false,
  });
  const { data: farmEvents } = useQuery({
    queryKey: ["farm-events", farm?.id],
    queryFn: () => fetchFarmEvents(farm!.id),
    enabled: !!farm && !herdsError,
    retry: false,
  });
  const { data: completions } = useQuery({
    queryKey: ["calendar-completions", farm?.id],
    queryFn: () => fetchCompletions(farm!.id),
    enabled: !!farm && !herdsError,
    retry: false,
  });
  const { data: calendarKnowledge } = useQuery({
    queryKey: ["calendar-knowledge"],
    queryFn: fetchCalendarKnowledge,
    staleTime: Infinity,
  });

  async function refreshCalendarData() {
    if (!farm) return;
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["herds", farm.id] }),
      queryClient.invalidateQueries({ queryKey: ["farm-events", farm.id] }),
      queryClient.invalidateQueries({ queryKey: ["calendar-completions", farm.id] }),
    ]);
  }

  const [adding, setAdding] = useState(false);
  const [draftPoints, setDraftPoints] = useState<LatLng[]>([]);
  const [draftAcres, setDraftAcres] = useState(0);
  const [fieldName, setFieldName] = useState("");
  const [fieldCrop, setFieldCrop] = useState("");
  const [plantingDate, setPlantingDate] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    if (!farm || draftPoints.length < 3 || !fieldName.trim()) return;
    setSaving(true);
    try {
      await createField({
        farmId: farm.id,
        name: fieldName.trim(),
        boundary: polygonToGeoJSON(draftPoints),
        acres: Math.round(draftAcres * 10) / 10,
        // Only what the farmer actually picked -- never a defaulted guess,
        // see FieldPredictionPanel's note on why.
        primaryCrop: fieldCrop || undefined,
        plantingDate: plantingDate || undefined,
      });
      await queryClient.invalidateQueries({ queryKey: ["fields", farm.id] });
      setAdding(false);
      setFieldName("");
      setFieldCrop("");
      setPlantingDate("");
      setDraftPoints([]);
      setDraftAcres(0);
    } finally {
      setSaving(false);
    }
  }

  function handleCancelAdd() {
    setAdding(false);
    setDraftPoints([]);
    setDraftAcres(0);
    setFieldName("");
    setFieldCrop("");
    setPlantingDate("");
  }

  // Fire-and-forget: this is a background save of what the farmer already
  // sees selected, so it shouldn't block the prediction they're about to
  // run or bounce the UI on a slow write. Refetch after so the persisted
  // value is what a reload shows.
  async function handleSeasonChange(fieldId: number, params: { primaryCrop?: string; plantingDate?: string }) {
    if (!farm) return;
    try {
      await updateFieldSeason(fieldId, params);
      await queryClient.invalidateQueries({ queryKey: ["fields", farm.id] });
    } catch (error) {
      console.error("Couldn't save this field's season details:", farmErrorMessage(error));
    }
  }

  async function handleDelete(fieldId: number) {
    if (!farm) return;
    await deleteField(fieldId);
    await queryClient.invalidateQueries({ queryKey: ["fields", farm.id] });
  }

  async function handleSignOut() {
    await supabase.auth.signOut();
    router.replace("/login");
  }

  if (loading || !session) {
    return (
      <div className="flex min-h-dvh items-center justify-center text-sm text-muted-foreground">Loading...</div>
    );
  }

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="flex flex-col gap-2 border-b border-border bg-card px-4 py-2.5 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <div className="flex items-center gap-3">
          <Link
            href="/map"
            aria-label="Back to map"
            className="flex items-center justify-center rounded-full p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <ArrowLeft className="size-4" aria-hidden="true" />
          </Link>
          <div>
            <h1 className="flex items-center gap-2 font-heading text-lg font-semibold text-card-foreground">
              <MapPinned className="size-4 text-primary" aria-hidden="true" />
              My Farm
            </h1>
            <p className="text-xs text-muted-foreground">{session.user.email}</p>
          </div>
        </div>
        <button
          type="button"
          onClick={handleSignOut}
          className="cursor-pointer self-start rounded-lg px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted sm:self-auto"
        >
          Sign out
        </button>
      </header>

      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-4 px-4 py-6 sm:px-6">
        {farmErrored && (
          <div className="rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
            <p className="font-medium">Couldn&apos;t load your farm.</p>
            <p className="mt-1 text-destructive/80">
              {farmErrorMessage(farmError)} -- if this says the
              &quot;farmers&quot; table wasn&apos;t found, run{" "}
              <code className="rounded bg-destructive/10 px-1 py-0.5">src/supabase_farm_schema.sql</code> once in
              your Supabase project&apos;s SQL editor.
            </p>
          </div>
        )}

        <div className="flex items-center justify-between">
          <h2 className="font-heading text-lg font-semibold text-foreground">Your fields</h2>
          {!adding && !farmErrored && (
            <button
              type="button"
              onClick={() => setAdding(true)}
              className="cursor-pointer rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground shadow-sm transition-opacity hover:opacity-90"
            >
              Add field
            </button>
          )}
        </div>

        {!fieldsLoading && !fields?.length && !adding && (
          <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-accent/40 p-8 text-center">
            <Sprout className="size-6 text-accent" aria-hidden="true" />
            <p className="text-sm text-muted-foreground">
              No fields yet -- add your first one to get predictions scoped to your own land instead of your
              county average.
            </p>
          </div>
        )}

        {!!fields?.length && (
          <ul className="space-y-2">
            {fields.map((field) => (
              <li key={field.id} className="rounded-xl border border-accent/40 bg-card px-4 py-3 shadow-sm">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-medium text-card-foreground">{field.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {field.acres ? `~${field.acres} acres` : "acreage unknown"}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleDelete(field.id)}
                    aria-label={`Delete ${field.name}`}
                    className="cursor-pointer rounded-full p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-destructive"
                  >
                    <Trash2 className="size-4" aria-hidden="true" />
                  </button>
                </div>
                {!!crops?.length && (
                  <FieldPredictionPanel
                    field={field}
                    crops={crops}
                    onSeasonChange={(params) => handleSeasonChange(field.id, params)}
                  />
                )}
              </li>
            ))}
          </ul>
        )}

        {adding && (
          <div className="space-y-3 rounded-xl border border-accent/40 bg-card p-4 shadow-sm">
            <FieldMap
              onChange={(points, acres) => {
                setDraftPoints(points);
                setDraftAcres(acres);
              }}
            />
            <div className="flex flex-wrap items-center gap-3">
              <input
                type="text"
                value={fieldName}
                onChange={(e) => setFieldName(e.target.value)}
                placeholder="Field name (e.g. North 80)"
                className="min-w-48 flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-primary"
              />
              {!!crops?.length && (
                <select
                  value={fieldCrop}
                  onChange={(e) => setFieldCrop(e.target.value)}
                  className="cursor-pointer rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-primary"
                >
                  <option value="" disabled>
                    Which crop?
                  </option>
                  {crops.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.display_name}
                    </option>
                  ))}
                </select>
              )}
              {/* Optional, but the highest-value thing a farmer can tell us --
                  it's what growth-stage modelling accumulates from. */}
              <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
                Planted
                <input
                  type="date"
                  value={plantingDate}
                  min={`${new Date().getFullYear() - 2}-01-01`}
                  max={`${new Date().getFullYear() + 1}-12-31`}
                  onChange={(e) => setPlantingDate(e.target.value)}
                  className="cursor-pointer rounded-lg border border-border bg-background px-2 py-2 text-sm text-foreground outline-none focus:border-primary"
                />
              </label>
              <span className="text-sm text-muted-foreground">
                {draftPoints.length >= 3 ? `~${draftAcres.toFixed(1)} acres` : `draw at least 3 points`}
              </span>
              <div className="ml-auto flex gap-2">
                <button
                  type="button"
                  onClick={handleCancelAdd}
                  className="cursor-pointer rounded-lg border border-border px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleSave}
                  disabled={draftPoints.length < 3 || !fieldName.trim() || saving}
                  className="cursor-pointer rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground shadow-sm transition-opacity hover:opacity-90 disabled:opacity-50"
                >
                  {saving ? "Saving..." : "Save field"}
                </button>
              </div>
            </div>
          </div>
        )}

        {farm && herdsError && (
          <div className="rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
            <p className="font-medium">Livestock and calendar aren&apos;t set up yet.</p>
            <p className="mt-1 text-destructive/80">
              {farmErrorMessage(herdsError)} -- run{" "}
              <code className="rounded bg-destructive/10 px-1 py-0.5">
                src/supabase_farm_migration_calendar.sql
              </code>{" "}
              once in your Supabase project&apos;s SQL editor.
            </p>
          </div>
        )}

        {farm && !herdsError && herds && calendarKnowledge && (
          <LivestockPanel
            farmId={farm.id}
            herds={herds}
            events={farmEvents ?? []}
            knowledge={calendarKnowledge}
            onChanged={refreshCalendarData}
          />
        )}

        {farm && !herdsError && herds && fields && (
          <FarmCalendar
            farmId={farm.id}
            fields={fields}
            herds={herds}
            events={farmEvents ?? []}
            completions={completions ?? []}
            onChanged={refreshCalendarData}
          />
        )}
      </main>
    </div>
  );
}
