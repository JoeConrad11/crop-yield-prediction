import { supabase } from "./supabase-client";
import type { CalendarCompletion, Farm, FarmEvent, Field, Herd } from "./farm-types";
import type { GeoJSONPolygon } from "./geo";

// Every farmer gets exactly one auto-created farm in Phase 1's UI -- the
// `farms` table stays multi-farm-capable (see src/supabase_farm_schema.sql)
// for when that's actually needed, but nothing in this file assumes more
// than one exists yet.
export async function ensureDefaultFarm(farmerId: string, email?: string): Promise<Farm> {
  const { error: upsertError } = await supabase
    .from("farmers")
    .upsert({ id: farmerId, display_name: email ?? null }, { onConflict: "id" });
  if (upsertError) throw upsertError;

  const { data: existing, error: selectError } = await supabase
    .from("farms")
    .select("*")
    .eq("farmer_id", farmerId)
    .order("created_at", { ascending: true })
    .limit(1)
    .maybeSingle();
  if (selectError) throw selectError;
  if (existing) return existing as Farm;

  const { data: created, error: insertError } = await supabase
    .from("farms")
    .insert({ farmer_id: farmerId, name: "My farm" })
    .select()
    .single();
  if (insertError) throw insertError;
  return created as Farm;
}

export async function fetchFields(farmId: number): Promise<Field[]> {
  const { data, error } = await supabase
    .from("fields")
    .select("*")
    .eq("farm_id", farmId)
    .order("created_at", { ascending: false });
  if (error) throw error;
  return data as Field[];
}

export async function createField(params: {
  farmId: number;
  name: string;
  boundary: GeoJSONPolygon;
  acres: number;
  primaryCrop?: string;
  plantingDate?: string;
}): Promise<Field> {
  const { data, error } = await supabase
    .from("fields")
    .insert({
      farm_id: params.farmId,
      name: params.name,
      boundary: params.boundary,
      acres: params.acres,
      primary_crop: params.primaryCrop ?? null,
      planting_date: params.plantingDate || null,
    })
    .select()
    .single();
  if (error) throw error;
  return data as Field;
}

// Crop and planting date change every season on the same physical field, so
// these are editable after creation -- unlike the boundary, which doesn't
// move. Phase 4b (see ../../ARCHITECTURE.md).
export async function updateFieldSeason(
  fieldId: number,
  params: { primaryCrop?: string | null; plantingDate?: string | null }
): Promise<Field> {
  const patch: Record<string, string | null> = {};
  if (params.primaryCrop !== undefined) patch.primary_crop = params.primaryCrop || null;
  if (params.plantingDate !== undefined) patch.planting_date = params.plantingDate || null;

  const { data, error } = await supabase
    .from("fields")
    .update(patch)
    .eq("id", fieldId)
    .select()
    .single();
  if (error) throw error;
  return data as Field;
}

export async function deleteField(fieldId: number): Promise<void> {
  const { error } = await supabase.from("fields").delete().eq("id", fieldId);
  if (error) throw error;
}

// ---- Smart farm calendar (src/supabase_farm_migration_calendar.sql) ----
// Only the farmer's inputs are stored; due dates are derived by the API.

export async function fetchHerds(farmId: number): Promise<Herd[]> {
  const { data, error } = await supabase
    .from("herds")
    .select("*")
    .eq("farm_id", farmId)
    .order("created_at", { ascending: true });
  if (error) throw error;
  return data as Herd[];
}

export async function createHerd(params: {
  farmId: number;
  species: string;
  name: string;
  headCount?: number | null;
}): Promise<Herd> {
  const { data, error } = await supabase
    .from("herds")
    .insert({
      farm_id: params.farmId,
      species: params.species,
      name: params.name,
      head_count: params.headCount ?? null,
    })
    .select()
    .single();
  if (error) throw error;
  return data as Herd;
}

// Events and completions point at a herd polymorphically (no foreign key),
// so removing a herd cleans them up here rather than relying on a cascade.
export async function deleteHerd(farmId: number, herdId: number): Promise<void> {
  for (const table of ["farm_events", "calendar_completions"]) {
    const { error } = await supabase
      .from(table)
      .delete()
      .eq("farm_id", farmId)
      .eq("subject_type", "herd")
      .eq("subject_id", herdId);
    if (error) throw error;
  }
  const { error } = await supabase.from("herds").delete().eq("id", herdId);
  if (error) throw error;
}

export async function fetchFarmEvents(farmId: number): Promise<FarmEvent[]> {
  const { data, error } = await supabase
    .from("farm_events")
    .select("*")
    .eq("farm_id", farmId)
    .order("event_date", { ascending: false });
  if (error) throw error;
  return data as FarmEvent[];
}

export async function addFarmEvent(params: {
  farmId: number;
  subjectType: "field" | "herd";
  subjectId: number;
  kind: string;
  eventDate: string;
}): Promise<FarmEvent> {
  const { data, error } = await supabase
    .from("farm_events")
    .insert({
      farm_id: params.farmId,
      subject_type: params.subjectType,
      subject_id: params.subjectId,
      kind: params.kind,
      event_date: params.eventDate,
    })
    .select()
    .single();
  if (error) throw error;
  return data as FarmEvent;
}

export async function deleteFarmEvent(eventId: number): Promise<void> {
  const { error } = await supabase.from("farm_events").delete().eq("id", eventId);
  if (error) throw error;
}

export async function fetchCompletions(farmId: number): Promise<CalendarCompletion[]> {
  const { data, error } = await supabase.from("calendar_completions").select("*").eq("farm_id", farmId);
  if (error) throw error;
  return data as CalendarCompletion[];
}

// One row per (subject, rule, occurrence). Ticking inserts it (idempotent via
// the table's unique constraint); un-ticking deletes it.
export async function setCompletion(params: {
  farmId: number;
  subjectType: "field" | "herd";
  subjectId: number;
  ruleId: string;
  occurrenceDate: string;
  done: boolean;
}): Promise<void> {
  if (params.done) {
    const { error } = await supabase.from("calendar_completions").upsert(
      {
        farm_id: params.farmId,
        subject_type: params.subjectType,
        subject_id: params.subjectId,
        rule_id: params.ruleId,
        occurrence_date: params.occurrenceDate,
      },
      { onConflict: "farm_id,subject_type,subject_id,rule_id,occurrence_date" }
    );
    if (error) throw error;
    return;
  }
  const { error } = await supabase
    .from("calendar_completions")
    .delete()
    .eq("farm_id", params.farmId)
    .eq("subject_type", params.subjectType)
    .eq("subject_id", params.subjectId)
    .eq("rule_id", params.ruleId)
    .eq("occurrence_date", params.occurrenceDate);
  if (error) throw error;
}
